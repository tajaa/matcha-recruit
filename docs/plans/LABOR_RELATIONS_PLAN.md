# Union / Collective-Bargaining-Agreement (CBA) Management — Implementation Plan

## Context

Matcha can describe union *law* (compliance registry already carries `nlra_organizing`,
`collective_bargaining`, `right_to_work`, `union_notification`, `strike_lockout_rules`,
`employee_representation`) and flag a company as unionized (`company_handbook_profiles.union_employees`).
It **cannot operate a unionized workforce**: there is no grievance workflow, no CBA contract store,
no just-cause/Weingarten handling on discipline, and no seniority / bargaining-unit / dues data on
the employee record. This plan adds that operational layer to the **full Matcha platform** (`/app/*`,
`ClientSidebar`, business `role='client'`) as a new `labor_relations` feature.

**Decisions (confirmed with user):**
- **Full suite, phased** — all four phases below, sequenced.
- **Bundled into Matcha-Pro** — `labor_relations` is stored `True` at bespoke signup (like
  `handbook_audit` / `credential_templates` / `compliance`). Pro gets it free; non-Pro tiers don't get
  it. NOT in any `TIER_REQUIRED_FEATURES` overlay — storing at signup (not overlaying at read time) is
  exactly what keeps it OFF personal Werk, which shares `signup_source='bespoke'` with `is_personal=true`.
  No Stripe add-on path.
- **Full AI** — Gemini clause extraction from the uploaded CBA PDF, grievance merit assessment, and
  just-cause analysis, all reusing the ER analyzer plumbing.

Everything is gated by `require_feature("labor_relations")` (backend) and `<FeatureGate feature="labor_relations">` (frontend).

---

## Cross-cutting conventions (apply to every phase)

- **One backend package** `server/app/matcha/routes/labor_relations/` following the `ir_incidents/` /
  `employees/` template (see `server/app/matcha/routes/CLAUDE.md`). Files: `cba.py`, `grievances.py`,
  `bargaining_units.py`, `arbitrations.py`, `_shared.py`, `__init__.py` (re-exports `grievances.router`
  as the package `router`). Mount once in `server/app/matcha/routes/__init__.py` with
  `prefix="/labor"`, `dependencies=[Depends(require_feature("labor_relations"))]`.
- **Pydantic models** in `server/app/matcha/models/labor_relations.py` (not inline — server convention).
- **Tenant isolation**: every endpoint derives `company_id = Depends(get_client_company_id)`
  (`server/app/matcha/dependencies.py`); never trust a path/body `company_id`; 404 on mismatch. New
  `lr_*` tables key on `company_id`; ALTERed `employees` rows key on `org_id` (existing convention).
- **Schema conventions** (match `progressive_discipline`/`er_cases`): UUID PK `gen_random_uuid()`,
  `company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE`, `created_at/updated_at
  TIMESTAMPTZ DEFAULT NOW()`, JSONB `DEFAULT '[]'::jsonb`, `CHECK (col IN (...))` enums,
  `idx_<table>_company` on `company_id`. Idempotent DDL (`CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`).
- **Migrations**: one Alembic revision per phase (`labor01`…`labor04`). At author time, chain
  `down_revision` off `cd server && ./venv/bin/python -m alembic heads` (302 migrations w/ merge points —
  do NOT hardcode a parent). Apply to **both** DBs: `./scripts/migrate-dev.sh` then
  `./scripts/migrate-prod.sh` (pre-cutover prod needs RDS + `--legacy`). Mirror `CREATE TABLE` into
  `database.py:init_db()` for fresh-DB parity (optional, matches convention). **Never auto-run Alembic —
  user approves each apply.**
- **Audit**: one `lr_audit_log` table + `_shared.py:write_audit(conn, entity_type, entity_id, actor, action, details)`
  called inside each state-change transaction (mirrors `discipline_audit_log` / `er_audit_log`).
- **AI**: thin new `services/labor_relations_ai.py` composes prompts and delegates to a reused
  `ERAnalyzer` (`server/app/matcha/services/er_analyzer.py:512`) — `_generate_content_async` (line 552)
  and `_generate_content_streaming` (line 583). Add a module-level `get_labor_analyzer()` singleton
  (mirror `get_ir_analyzer`); never instantiate Gemini per request. CBA PDF→text via
  `er_document_parser.py:DocumentParser.extract_text_from_bytes` (line 150). Long extraction runs in a
  Celery task modeled on `er_document_processing.py`.
- **Storage**: CBA PDFs + grievance evidence are sensitive → `storage.upload_private_file(bytes, name,
  prefix="cba-documents", content_type="application/pdf")` → `s3://` URI; serve via presigned URL
  (`storage.get_presigned_download_url`, 900s). Never the public `upload_file`.

---

## Pro bundling (do first — unblocks the gate)

`labor_relations` ships **inside Matcha-Pro**, stored `True` at company creation exactly like
`handbook_audit` / `credential_templates`. No Stripe path, no add-on subscription.

1. **Flag** — add `"labor_relations": False` to `DEFAULT_COMPANY_FEATURES` in
   `server/app/core/feature_flags.py`. Do NOT add to any `TIER_REQUIRED_FEATURES` overlay — storing at
   signup (not overlaying at read time) is exactly what keeps it OFF personal Werk, which shares
   `signup_source='bespoke'` with `is_personal=true`.
2. **Self-signup bespoke** — `server/app/core/routes/auth.py:1856-1860` (the business bespoke branch
   that already sets `incidents` / `handbook_audit` / `credential_templates` True): add
   `bespoke_features["labor_relations"] = True`.
3. **Admin tier preset** — `server/app/core/routes/admin.py:9809` (`_TIER_FEATURE_PRESETS["bespoke"]`,
   currently bare `dict(DEFAULT_COMPANY_FEATURES)`): set
   `{**dict(DEFAULT_COMPANY_FEATURES), "labor_relations": True}` so admin-created / admin-tier-changed Pro
   companies (the main post-sale path) get it too.
4. **Backfill existing Pro rows** — stored-at-signup ≠ overlay, so companies created before this change
   won't have the flag. One-time data migration (fold into `labor01`):
   `UPDATE companies SET enabled_features = jsonb_set(COALESCE(enabled_features,'{}')::jsonb,
   '{labor_relations}', 'true') WHERE (signup_source IN ('bespoke','invite') OR signup_source IS NULL)
   AND is_personal IS NOT TRUE;` Apply to dev + prod like any migration. (Alternative: leave existing
   rows to the admin per-company feature toggle.)
5. **Frontend** — no subscribe CTA (bundled, not purchasable). Lower-tier users who URL-hop to
   `/app/labor` get the standard `<FeatureGate>` → `<UpgradeUpsellCard>` ("talk to sales") automatically.

---

## Phase 1 (MVP value) — CBA document store + Grievance workflow + deadline cron + AI

**Why first:** grievance handling with contractual step-deadlines is the single most union-distinctive
capability the platform completely lacks and cannot fake with existing modules. CBA storage is its
necessary companion (a grievance cites CBA clauses).

### Migration `labor01_cba_and_grievances.py`

- **`lr_cbas`** — contract metadata (PDF in S3): `id, company_id, union_name, union_local,
  bargaining_unit_desc TEXT, effective_date, expiration_date, status CHECK
  ('draft','active','expired','superseded','in_negotiation'), document_storage_path, document_filename,
  extracted_text TEXT, extraction_status CHECK ('pending','processing','complete','failed','skipped'),
  renewal_alert_days INT DEFAULT 90, grievance_step_config JSONB DEFAULT '[]'::jsonb, metadata JSONB,
  created_by, created_at, updated_at`. Indexes: company; partial on `expiration_date WHERE status='active'`.
  - `grievance_step_config` shape (the contractual-deadline source of truth, AI-seeded + HR-confirmed):
    `[{"step":1,"name":"Supervisor","file_within_days":10,"respond_within_days":5,"day_basis":"calendar"}, …]`.
- **`lr_cba_clauses`** — clause library: `id, cba_id, company_id (denorm), article_number, title,
  clause_text TEXT, category CHECK ('wages','hours','seniority','grievance_procedure','discipline',
  'just_cause','overtime','benefits','union_security','management_rights','health_safety','layoff_recall',
  'holidays_leave','other'), source CHECK ('manual','ai_extracted'), ai_confidence NUMERIC(4,3),
  sort_order INT, created_at, updated_at`.
- **`lr_grievances`** — the core record: `id, company_id, grievance_number UNIQUE (GRV-YYYY-NNNN),
  cba_id FK, grievant_employee_id FK→employees SET NULL, is_class_grievance BOOL, steward_employee_id FK,
  steward_name_external VARCHAR, title, description, grievance_type CHECK ('discipline','discharge',
  'contract_interpretation','pay_wages','seniority','overtime','working_conditions','health_safety',
  'management_rights','past_practice','other'), incident_date DATE, filed_date DATE, current_step INT
  DEFAULT 1, status CHECK ('draft','filed','in_progress','advanced','resolved','withdrawn','denied',
  'arbitration','settled'), resolution CHECK ('granted','denied','partially_granted','withdrawn',
  'settled','arbitrated_win','arbitrated_loss'), resolution_summary, resolved_at, linked_discipline_id
  FK→progressive_discipline SET NULL, linked_er_case_id FK→er_cases SET NULL, documents JSONB,
  created_by, assigned_to, created_at, updated_at`. Indexes: company; (company,status); grievant.
- **`lr_grievance_violated_clauses`** — M:N: `(grievance_id, clause_id)` PK.
- **`lr_grievance_steps`** — per-step timeline w/ deadlines: `id, grievance_id, company_id (denorm),
  step_number, step_name, status CHECK ('pending','active','responded','advanced','resolved','skipped',
  'missed_deadline'), filed_at, deadline_to_respond DATE, deadline_to_advance DATE, response_received_at,
  heard_by_user_id, management_response TEXT, union_position TEXT, outcome CHECK ('granted','denied',
  'partially_granted','advanced'), deadline_alert_sent BOOL DEFAULT FALSE, created_at, updated_at,
  UNIQUE(grievance_id, step_number)`. Partial index on `deadline_to_respond WHERE status='active' AND
  deadline_alert_sent=FALSE` (drives the cron).
- **`lr_audit_log`** — shared: `id, company_id, entity_type, entity_id, actor_user_id, action, details
  JSONB, created_at`. Index `(entity_type, entity_id, created_at DESC)`.
- **Seed** the scheduler row (pattern from the `benefit_eligibility_sync` seed):
  `INSERT INTO scheduler_settings (task_key, display_name, description, enabled) VALUES
  ('grievance_deadline_alerts', …, false) ON CONFLICT DO NOTHING`.

### Backend routers

- **`cba.py`**: `GET/POST /cbas`, `GET/PATCH/DELETE /cbas/{id}`, `POST /cbas/{id}/document` (multipart →
  `upload_private_file`, queue extraction task), `GET /cbas/{id}/document` (presigned),
  `POST /cbas/{id}/extract-clauses` (202, async re-run), `GET/POST /cbas/{id}/clauses`,
  `PATCH/DELETE /cbas/{id}/clauses/{clause_id}` (confirm/correct AI rows).
- **`grievances.py`** (package `router`): `GET /grievances` (filters incl. `overdue=true`),
  `POST /grievances` (auto `grievance_number`; seed `lr_grievance_steps` from CBA `grievance_step_config`;
  compute step-1 deadlines), `GET /grievances/{id}`, `PATCH /grievances/{id}`,
  `POST /grievances/{id}/file` (draft→filed, activate step 1), `POST /grievances/{id}/steps/{n}/respond`,
  `POST /grievances/{id}/advance`, `POST /grievances/{id}/resolve`, `POST /grievances/{id}/withdraw`,
  `POST /grievances/{id}/clauses` (attach/detach M:N), `POST /grievances/{id}/documents`,
  `GET /grievances/{id}/audit-log`, `POST /grievances/{id}/assess-merit` (AI, SSE),
  `GET /grievances/dashboard` (counts by status/step + overdue list).
- **`_shared.py`**: `compute_step_deadlines(step_config, step_number, anchor_date)` — the edge-case-heavy
  core: calendar-vs-working-days (per-CBA `day_basis`, default calendar), missing config fallback
  `[10,5]` + a "no grievance procedure on file" warning, anchor ambiguity (incident vs discovery — store
  `incident_date`, allow HR override). Holiday roll-forward is a **known v1 gap** (calendar only).
  Plus `write_audit(...)` and `next_grievance_number(conn, company_id)`.

### AI (`services/labor_relations_ai.py`)

- `extract_clauses_from_cba(extracted_text)` → JSON list (article#, title, text, category, confidence) +
  best-effort `grievance_step_config` parse. Runs in Celery `app/workers/tasks/cba_clause_extraction.py`
  (model on `er_document_processing.py`): PDF → `extract_text_from_bytes` → store `extracted_text` →
  Gemini → insert `lr_cba_clauses` (`source='ai_extracted'`) → `extraction_status='complete'`. HR
  confirms via the clauses PATCH endpoint. **The deadline engine must not enforce off an unconfirmed AI
  parse** — show a "verify grievance procedure" gate on the CBA until a human confirms `grievance_step_config`.
- `assess_grievance_merit(grievance, cited_clause_texts)` → streamed text grading the alleged violation
  against actual contract language (strengths/weaknesses, settlement posture). SSE via
  `StreamingResponse(media_type="text/event-stream")` like ER analysis.

### Celery cron `app/workers/tasks/grievance_deadline_alerts.py`

Model on `discipline_expiry.py`: gate on `_is_scheduler_enabled("grievance_deadline_alerts")`; register
the dispatch in `celery_app.py` alongside `discipline_expiry` (line ~187). Query `lr_grievance_steps`
where `status='active' AND deadline_to_respond <= NOW()+N days AND deadline_alert_sent=FALSE`; email
`assigned_to` + steward via `get_email_service()`; set `deadline_alert_sent=TRUE`; flip truly-missed
steps to `status='missed_deadline'` (idempotent).

### Frontend

- Sidebar — add to the **HR Ops** group in `client/src/components/ClientSidebar.tsx` (next to Discipline,
  line 21): `{ to: '/app/labor', icon: Scale, label: 'Labor Relations', feature: 'labor_relations' }`
  (group items auto-filter on `hasFeature`).
- Pages under `client/src/pages/app/`: `LaborRelations.tsx` (dashboard: grievance counts, overdue-deadline
  banner, CBA-expiration warnings, tabs [Grievances | CBAs]), `GrievanceDetail.tsx` (vertical step timeline
  w/ per-step deadline/response/outcome, violated-clause chips, AI merit-assessment streaming panel —
  reuse the ER copilot streaming-panel pattern, document list), `CBADetail.tsx` (metadata, PDF
  upload/download, clause-library table w/ AI rows badged + confirmable, editable `grievance_step_config`).
- Routes in `client/src/App.tsx`: `/app/labor`, `/app/labor/grievances/:id`, `/app/labor/cbas/:id`, each
  wrapped `<FeatureGate feature="labor_relations">`.
- Components under `client/src/components/labor/` (mirror `er/`); reuse `ui/` primitives. API methods in a
  new `client/src/api/laborClient.ts`; domain hooks under `client/src/hooks/labor/`.

---

## Phase 2 — Bargaining units + seniority on employees

### Migration `labor02_bargaining_units.py`

- **`lr_bargaining_units`**: `id, company_id, name, union_name, union_local, cba_id FK→lr_cbas SET NULL,
  description, is_active BOOL DEFAULT TRUE, created_at, updated_at, UNIQUE(company_id, name)`.
- **ALTER `employees`** (idempotent `information_schema.columns` guard, as `database.py` does for the
  ALTER-heavy employees table): `seniority_date DATE` (distinct from `start_date` — bridges breaks in
  service), `bargaining_unit_id UUID FK→lr_bargaining_units SET NULL`, `is_union_member BOOL DEFAULT FALSE`,
  `union_dues_amount NUMERIC(10,2)`, `union_dues_frequency VARCHAR CHECK ('per_paycheck','monthly','annual')`,
  `seniority_rank_override INT`. Partial index `(org_id, bargaining_unit_id) WHERE bargaining_unit_id IS NOT NULL`.
- Also add `bargaining_unit_id UUID FK` to `lr_cbas` (back-links the Phase-1 free-text `bargaining_unit_desc`).

### Backend `bargaining_units.py`

`GET/POST /bargaining-units`, `GET/PATCH/DELETE /bargaining-units/{id}`,
`GET /bargaining-units/{id}/seniority-list` (ordered by `seniority_date ASC`, tie-break
`seniority_rank_override` → `start_date` → `last_name`), `GET /bargaining-units/{id}/members`,
`GET /bargaining-units/{id}/dues-roster`.

**Extend employees CRUD** — `server/app/matcha/routes/employees/crud.py`: add the 6 fields to the
create/update Pydantic models + SELECT/UPDATE. Per Code-Modification Rules, also update the package's
`_shared.py` and `bulk_upload.py` (CSV header map + template) so union fields import — keep RFC-2606
reserved domains in the template. Seniority-list view is a new tab on `Employees.tsx` (reuse the employee
table component).

**Edge cases:** seniority ≠ hire date (rehires/transfers — hence separate column + manual override);
deterministic tie-break; **right-to-work**: in RTW states (`employees.work_state`) dues/membership cannot
be compelled, so `is_union_member`/`union_dues_amount` are independently settable and NOT auto-derived
from unit coverage — surface the registry's `right_to_work` rule per state.

---

## Phase 3 — Just-cause + Weingarten (EXTEND existing discipline; no new module)

### Migration `labor03_discipline_union_fields.py` — ALTER `progressive_discipline`

`cba_clause_id UUID FK→lr_cba_clauses SET NULL`, `just_cause_checklist JSONB DEFAULT '{}'::jsonb`
(the 7 Daugherty tests: notice / reasonable_rule / investigation / fair_investigation / proof /
equal_treatment / penalty_proportionate, each w/ optional notes), `just_cause_complete BOOL`,
`weingarten_invoked BOOL`, `union_rep_present BOOL`, `union_rep_name VARCHAR`,
`union_rep_employee_id UUID FK→employees SET NULL`, `linked_grievance_id UUID FK→lr_grievances SET NULL`.
Non-union companies leave these default; UI hides them.

### Backend (extend, don't add a router)

- Extend `IssueRequest` model + thread new fields into the INSERT in
  `server/app/matcha/services/discipline_engine.py` (`issue_discipline_with_supersede`, the column-list
  INSERT ~line 380).
- **Weingarten gate** at the `draft→pending_meeting` transition in `server/app/matcha/routes/discipline.py`
  (`issue_record`, ~line 192): if the employee has `bargaining_unit_id` and `weingarten_invoked=TRUE`,
  require `union_rep_present` (or explicit waiver) before allowing the investigatory-meeting transition,
  else 400 with a Weingarten explanation. Soft business rule, not a DB constraint.
- New `POST /discipline/records/{id}/just-cause-analysis` — AI (reuse analyzer): given facts + cited CBA
  clause + the 7-test framework, stream an analysis flagging weak tests. Union sub-fields are
  presentation-gated client-side on `hasFeature('labor_relations')`; server treats them as nullable.

### Frontend

Extend `client/src/pages/app/Discipline.tsx` + `DisciplineDetail.tsx`: when
`hasFeature('labor_relations')` AND the employee has a `bargaining_unit_id`, show a "Union / Just Cause"
section — 7-test checklist, Weingarten toggles, CBA-clause picker (from `/labor/cbas/{id}/clauses`), a
"Run just-cause analysis" button (streams into the existing analysis panel), and a "Create grievance from
this discipline" button → POST `/labor/grievances` pre-filled `linked_discipline_id` +
`grievance_type='discipline'`.

---

## Phase 4 — Arbitration + ULP-charge link + dues write-back (mostly reuse)

### Migration `labor04_arbitration.py`

- **`lr_arbitrations`**: `id, company_id, grievance_id FK→lr_grievances CASCADE, case_number,
  arbitrator_name, arbitration_service ('AAA','FMCS','state_board','private'), demand_filed_date,
  hearing_date, briefs_due_date, status CHECK ('demand_filed','arbitrator_selection','scheduled','heard',
  'briefing','awarded','settled','withdrawn'), award_date, award_outcome CHECK ('company_win','union_win',
  'split','remanded'), award_summary, estimated_cost NUMERIC(12,2), documents JSONB, created_by, created_at,
  updated_at`. Indexes: company; grievance.
- **ALTER `agency_charges`** add `grievance_id UUID FK→lr_grievances SET NULL`.

### Reuse (no new tables)

- **NLRB / ULP** — `agency_charges` already has `charge_type='nlrb'` with full CRUD in
  `pre_termination.py` (lines 474-666). A "File ULP charge" button on the grievance detail calls the
  existing POST with `charge_type='nlrb'` + the new `grievance_id`. Surface existing charge endpoints in
  the Labor Relations UI. **Do not build a new ULP table.**
- **Dues write-back** — reuse the Finch deductions path (`/provisioning/hris/benefits`, flag
  `hris_deductions`). A "push dues as deduction" action on `/labor/bargaining-units/{id}/dues-roster`
  calls the existing Finch create-deduction with per-member `union_dues_amount`. Gate on BOTH
  `labor_relations` AND `hris_deductions`. Provider matrix (QuickBooks/Gusto/ADP yes, Square no) already
  handled. **No new HRIS code.**

### Backend / Frontend

Small `arbitrations.py` (CRUD + hearing-date reminder reusing the deadline-cron pattern). Frontend:
"Arbitration" tab on `GrievanceDetail.tsx`; a labor-relations cost dashboard (arbitration spend + ULP
exposure) reusing the dashboard aggregation.

---

## Sequencing & dependencies

```
Pro bundling (flag + store-at-signup + backfill)  ← do first; unblocks the gate
Phase 1 (CBA + grievances + cron + AI)      ← MVP value, ships alone
  └ Phase 2 (units + seniority)             ← independent value; adds FK target for lr_cbas.bargaining_unit_id
      └ Phase 3 (just-cause/Weingarten)     ← needs P1 clauses + P2 unit membership (Weingarten gate)
          └ Phase 4 (arbitration/ULP/dues)  ← needs P1 grievances; reuses agency_charges + Finch
```
Phases 1 and 2 are independently shippable. Phase 3 needs P1 (clauses) and ideally P2 (unit membership).
Phase 4 is pure add-on reuse.

## Risks / edge cases

1. **Contractual-deadline computation** (highest risk): working-vs-calendar days, holiday roll-forward,
   anchor ambiguity (incident vs discovery), tolling (mutual extensions). v1 = calendar days +
   per-CBA `day_basis` config + manual override + explicit "holidays not handled" note.
2. **Multi-CBA companies** — several units, each under a different CBA with different grievance
   procedures. Schema supports it (grievance→cba_id→step_config; unit→cba_id); UI must always scope a
   grievance to its CBA so the right deadlines apply.
3. **Right-to-work** — decouple dues/membership from unit coverage (Phase 2).
4. **AI is advisory** — every `ai_extracted` clause and the parsed `grievance_step_config` is
   HR-confirmable before the deadline engine relies on it (verify-gate on the CBA).
5. **PII / privilege** — CBA + grievance docs use `upload_private_file` + presigned only; grievance
   investigations that overlap ER cases link via `linked_er_case_id` (no evidence duplication).
6. **External steward** — stewards/business agents often aren't employees → both `steward_employee_id`
   FK and `steward_name_external` text.
7. **Migration drift** — apply every revision to dev AND prod (+ `--legacy` pre-cutover); chain
   `down_revision` off live `alembic heads`.

## Reuse vs build

| Concern | Decision | Reuse target |
|---|---|---|
| Pro bundling | store at signup | `auth.py:1856-1860` + `admin.py:9809` preset; backfill existing bespoke rows in `labor01` |
| CBA PDF storage | reuse | `storage.upload_private_file` / `get_presigned_download_url` |
| CBA→text | reuse | `er_document_parser.py:DocumentParser.extract_text_from_bytes` (line 150) |
| Clause-extract / merit / just-cause AI | reuse plumbing | `ERAnalyzer` (`er_analyzer.py:512`, `_generate_content_async/_streaming`) + Celery `er_document_processing.py` |
| Grievance workflow | **build new** | — (the core differentiator) |
| Deadline cron | reuse pattern | `discipline_expiry.py` + `scheduler_settings` + `celery_app.py:187` dispatch |
| Just-cause / Weingarten | **extend** | ALTER `progressive_discipline`; edit `discipline.py` + `discipline_engine.py` INSERT (~380) |
| Union-law knowledge | already exists | `compliance_registry.py` (`nlra_organizing`, `right_to_work`, …) |
| Units / seniority | new table + extend | ALTER `employees`; edit `employees/crud.py` + `bulk_upload.py` |
| NLRB / ULP | reuse, add FK | `agency_charges` + `pre_termination.py` CRUD (474-666) |
| Dues write-back | reuse | Finch `/provisioning/hris/benefits` + `hris_deductions` flag |

## Verification (end-to-end, per phase)

- **Schema**: `./scripts/migrate-dev.sh` then `cd server && ./venv/bin/python -m alembic current` matches
  the new head; spot-check tables with `\d lr_grievances` over the dev tunnel.
- **Backend**: `cd server && ./venv/bin/python run.py` (:8001). With a dev company that has
  `labor_relations` on: create a CBA, upload a sample CBA PDF, confirm the Celery clause-extraction job
  populates `lr_cba_clauses` + a draft `grievance_step_config`; file a grievance and confirm
  `lr_grievance_steps` seed with computed deadlines; advance a step; hit `/grievances/{id}/assess-merit`
  and confirm the SSE stream. Toggle the flag off → confirm `require_feature` 403 (FE shows upsell).
- **Cron**: enable the `grievance_deadline_alerts` scheduler row, set a step deadline in the past, run the
  task manually, confirm the email fires (to a reserved-domain test address) and `deadline_alert_sent` flips.
- **Pro bundling**: create a fresh bespoke company (self-signup + admin tier-set) → confirm
  `enabled_features.labor_relations=true` on `/auth/me`. Run the backfill → confirm existing bespoke
  companies flip on and personal-Werk (`is_personal=true`) rows stay off. Confirm a Lite/X company URL-
  hopping to `/app/labor` gets the upsell, not access.
- **Tests**: add `server/tests/labor_relations/` modeled on the IR-incidents suite (the passing model per
  `server/CLAUDE.md`); DB-mutating tests are manual-run only, reserved-domain data only.
- **Frontend**: `npx tsc --noEmit` in `client/`; click through `/app/labor` dashboard → grievance detail
  step timeline → CBA clause confirm.
