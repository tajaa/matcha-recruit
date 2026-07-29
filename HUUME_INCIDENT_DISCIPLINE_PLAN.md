# Huume skill: incident-triggered disciplinary action with HR approval — technical plan (v2, verified)

**Completeness self-rating: 0.96** (see audit at bottom). Every factual claim below was verified
against the working tree; file:line references are from today's `huume` branch.

## Context

Sixth Huume skill closing the incident→discipline loop: incident → handbook policy check →
drafted disciplinary action (company template or scratch) → HR approval or documented denial →
manager delivery → signed letter filed on both the incident and the employee file. Review of the
original draft plan found 4 blocking gaps (approval-gate bypass, remedial-training-at-draft,
employee_documents unique-index collision, incident-doc CHECK), ~8 wrong citations, and 2 user
decisions, now made: **(1)** HR approvers = designated (`clients.is_hr_approver`) with fallback
to all business admins; **(2)** defer the admin employee-documents tab (row is written; signed
PDF stays linked on DisciplineDetail; portal shows it to the employee).

Key verified facts the design leans on:
- `progressive_discipline` bootstrap `er_copilot.py:107-137`; status CHECK
  `('draft','pending_meeting','pending_signature','active','completed','expired','escalated')`;
  engine hardcodes `'draft'` at INSERT; **no** approval/incident/template columns exist.
- 6 `transition_status` callsites (`discipline.py:349,454,552,608,730,751`), all with
  `expected_from` lists that include `'draft'` on the signature paths — the bypass.
- `issue_discipline_with_supersede` (`discipline_engine.py:359-385`): keyword-only enumerated
  params, hardcoded 23-column INSERT, assigns remedial training **inside its transaction at
  status='draft'** (`:440-456`).
- `employee_documents`: tenant col `org_id`; partial unique
  `(employee_id, doc_type) WHERE status IN ('pending_signature','signed')`
  (`bootstrap/leads_policies.py:341-352`); `doc_type` VARCHAR(50), no CHECK; handbook embeds ids
  (`handbook:<id>:<version>`).
- `ir_incident_documents.document_type` CHECK `('photo','form','statement','other')`
  (`bootstrap/incidents.py:66`) + route allowlist (`ir_incidents/documents.py:48`) + client
  options (`IRDocumentPanel.tsx:7-10`).
- `ir_incident_analysis.analysis_type` CHECK **already contains `'policy_mapping'`** with
  `UNIQUE(incident_id, analysis_type)` (`bootstrap/incidents.py:88,92`); reader contract =
  `PolicyMappingAnalysis` (`models/ir/analysis.py:147-185`).
- Huume: `LOOKUP_TOPICS` already has `discipline` + `policies` (`tools.py:26-30`, handlers
  `onboarding_skill.py:451-483`); `SHOW_RECORD_TYPES` lacks `discipline` (`tools.py:34`);
  `_HUUME_ACTION_REQUIRED_FEATURE` at `actions.py:93-103`; `draft_discipline` bespoke arm at
  `agent.py:468-519`; table-driven arm `agent.py:521-557` over `_HR_OPS_TOOL_SPECS`
  (`agent.py:210-255`); `cancel_staged` message switch `agent.py:606-611`; state block is a
  **per-type switch** (`prompt.py:29-60`).
- `handbook_pilot.build_corpus(grounding, *, with_full_text=False)` is pure;
  `gather_grounding(conn, company_id, session)` is the DB half; non-route precedent
  `huume/handbook_skill.py:153-164`. `validate_citations(evidence_map, index)` is pure
  (`services/_shared/citations.py:31`, re-exported by `legal_defense`).
- `discipline_notifications.dispatch(*, record, action, notify_grandparent=True, skip_user_id=None)`
  (`:147-153`); `_TITLES` has exactly 5 keys and `dispatch` early-returns on unknown actions;
  recipient resolution is inline (manager CTE `:47-90`, HR set `:97-110` = all active
  `role='client'` via `clients`).
- Alembic has **5 heads** (`hrpush01`, `nldesign01`, `payequity02`, `trainmap01`, `zzzzcappe25`)
  — repo runs `alembic upgrade heads`; chain the new migration off `hrpush01`.
- `employees.job_title VARCHAR(150)` exists (migration `a4b5c6d7e8f9`); `_load_employee` already
  selects it (`discipline.py:132-145`). No HR-approver concept exists anywhere (verified).
- `discipline_expiry` sweeps only `status='active'` — drafts are never auto-touched.
- The copilot close path sends no notifications and there is **no queue anywhere** in
  `hr_proactive_push` — sweeps scan source tables with SQL `NOT EXISTS (ledger)`.

---

## 1. Migration — `server/alembic/versions/discipapp01_incident_discipline_approval.py`

```python
"""Incident-triggered discipline: approval state, templates, sweep ledger.

revision = "discipapp01"
down_revision = "hrpush01"   # 5 heads is normal here; migrate scripts run `upgrade heads`
"""
```

`upgrade()` — set-based SQL, in this order (templates table BEFORE the FK that points at it):

```sql
-- 1. Letter templates (deterministic resolver; placeholder body rendered server-side)
CREATE TABLE IF NOT EXISTS company_discipline_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    infraction_type VARCHAR(64),          -- NULL = any infraction
    discipline_type VARCHAR(30),          -- NULL = any level
    body TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_company_discipline_templates_default
  ON company_discipline_templates(company_id) WHERE is_default AND is_active;
CREATE INDEX IF NOT EXISTS idx_company_discipline_templates_company
  ON company_discipline_templates(company_id) WHERE is_active;

-- 2. Approval state + provenance on the record itself (one decision, one actor — not a workflow table)
ALTER TABLE progressive_discipline
  ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) NOT NULL DEFAULT 'not_required',
  ADD COLUMN IF NOT EXISTS approval_requested_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS approved_by UUID REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS approval_decided_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS denial_reason TEXT,
  ADD COLUMN IF NOT EXISTS source_incident_id UUID REFERENCES ir_incidents(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS template_id UUID REFERENCES company_discipline_templates(id) ON DELETE SET NULL,
  -- GAP-2 fix: remedial training named at draft time is STAGED here and only
  -- assigned at approval; a denied record must leave no training behind.
  ADD COLUMN IF NOT EXISTS pending_remedial_requirement_id UUID REFERENCES training_requirements(id) ON DELETE SET NULL;
ALTER TABLE progressive_discipline
  ADD CONSTRAINT progressive_discipline_approval_status_check
  CHECK (approval_status IN ('not_required','pending','approved','denied'));

-- 3. New terminal status. Default PG name for the inline column CHECK; verified none of the
--    6 transition_status expected_from lists contains 'denied', so the value is inert to them.
ALTER TABLE progressive_discipline DROP CONSTRAINT IF EXISTS progressive_discipline_status_check;
ALTER TABLE progressive_discipline ADD CONSTRAINT progressive_discipline_status_check
  CHECK (status IN ('draft','pending_meeting','pending_signature','active','completed','expired','escalated','denied'));

CREATE INDEX IF NOT EXISTS idx_progressive_discipline_approval
  ON progressive_discipline(company_id, approval_status) WHERE approval_status = 'pending';
CREATE INDEX IF NOT EXISTS idx_progressive_discipline_source_incident
  ON progressive_discipline(source_incident_id) WHERE source_incident_id IS NOT NULL;

-- 4. HR-approver designation (user decision #1). Shapes notification audience only —
--    authorization stays require_admin_or_client.
ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_hr_approver BOOLEAN NOT NULL DEFAULT FALSE;

-- 5. GAP-4 fix: signed letters filed against the incident get a real label (3 duplicated
--    vocabularies — DB CHECK here, route allowlist, client options — all widened in this PR).
ALTER TABLE ir_incident_documents DROP CONSTRAINT IF EXISTS ir_incident_documents_document_type_check;
ALTER TABLE ir_incident_documents ADD CONSTRAINT ir_incident_documents_document_type_check
  CHECK (document_type IN ('photo','form','statement','other','disciplinary'));

-- 6. Sweep dedupe ledger — one-shot-ever per incident, INCLUDING "checked, nothing found"
--    (thread_id NULL), or clean incidents are re-Gemini'd every cycle.
CREATE TABLE IF NOT EXISTS discipline_policy_sweep_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    incident_id UUID NOT NULL UNIQUE REFERENCES ir_incidents(id) ON DELETE CASCADE,
    thread_id UUID,
    finding_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Scheduler row, seeded DISABLED (repo convention — hrpush01:60-80 is the template)
INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
VALUES ('discipline_policy_sweep', 'Incident Policy-Check Sweep',
        'Checks closed incidents against the company handbook and opens a pre-briefed Huume thread on a finding. Gemini per incident; default off.',
        false, 25)
ON CONFLICT (task_key) DO NOTHING;
```

`downgrade()`: drop in reverse (scheduler row DELETE, sweep table, restore both CHECKs to their
prior value lists, drop the 8 columns + `clients.is_hr_approver`, drop templates table).
Rehearse with `MIGRATE_REHEARSAL=1` against dev before committing anything beyond the file.

### Bootstrap parity (same PR)

- `server/app/database/bootstrap/er_copilot.py` — add `company_discipline_templates` CREATE +
  extend the `progressive_discipline` CREATE with the 8 new columns, the widened status CHECK,
  **and backfill the 5 columns already missing** (`occurrence_dates`, `compliance_check`,
  `advisory_ack_reason`, `situation_narrative`, `remedial_requirement_id` — live drift from
  `discipcomp01`/`trainint01`; a fresh bootstrap DB currently breaks every discipline read).
  Add `discipline_policy_sweep_log`.
- `server/app/database/bootstrap/incidents.py:66` — widen the `ir_incident_documents` CHECK.
- `server/app/database/bootstrap/identity.py` — `is_hr_approver` on the `clients` CREATE.
- `server/app/database/bootstrap/portal_chat.py:225-236` — add the
  `discipline_policy_sweep` row to the seed VALUES list.

---

## 2. `server/app/matcha/services/discipline/discipline_templates.py` (NEW)

```python
"""Company letter templates for disciplinary actions.

Resolution is deterministic, never model-chosen; rendering is server-side over a
CLOSED placeholder vocabulary. Unknown placeholders survive verbatim — a silently
emptied clause in a legal document is worse than a visible {{token}}."""

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
DISCIPLINE_TEMPLATE_PLACEHOLDERS: frozenset[str] = frozenset({
    "employee_name", "employee_title", "manager_name", "company_name", "issued_date",
    "infraction_type", "discipline_type", "occurrence_dates", "incident_number",
    "policy_citations", "description", "expected_improvement", "review_date",
})

def resolve_template(templates: list[dict], *, infraction_type: str,
                     discipline_type: str) -> Optional[dict]:
    """Pure. exact (infraction_type, discipline_type) → infraction_type-only →
    company default → None (draft from scratch). Inactive rows excluded by the
    caller's query; ties broken by newest updated_at."""

def render_template(body: str, values: dict[str, Optional[str]]) -> tuple[str, list[str]]:
    """Pure. Returns (rendered, missing_fields): known placeholders whose value
    is empty/None render as '' AND are reported in missing_fields so the Huume
    staging can surface 'no manager on file' instead of shipping a blank."""

async def list_templates(conn, company_id: UUID, *, include_inactive: bool = False) -> list[dict]
async def upsert_template(conn, company_id: UUID, *, template_id: Optional[UUID], name: str,
                          infraction_type: Optional[str], discipline_type: Optional[str],
                          body: str, is_default: bool, is_active: bool,
                          created_by: Optional[UUID]) -> dict
    # is_default=True first clears the previous default IN THE SAME TRANSACTION —
    # the partial unique index rejects the write otherwise.
async def deactivate_template(conn, company_id: UUID, template_id: UUID) -> bool  # soft delete

async def build_placeholder_values(conn, *, company_id: UUID, employee: dict,
                                   record_fields: dict, incident: Optional[dict],
                                   policy_citations: list[str]) -> dict[str, Optional[str]]
    # employee_title ← employees.job_title; manager_name ← second lookup on
    # employees.manager_id (first/last name), None when unset (→ missing_fields).
```

`discipline_policy_mapping` is deliberately NOT extended with a template FK — the resolver keys
on `infraction_type` already; a second source of truth could disagree.

---

## 3. `server/app/matcha/services/discipline/discipline_policy_check.py` (NEW)

```python
"""Incident-narrative × handbook policy check. REPORTS, NEVER ADJUDICATES:
output carries candidate violations with citations and confidence — no
discipline level, no legality verdict. The deterministic
discipline_compliance gate remains the only thing that can block, at
record-write time, unchanged. Pool-free-safe: takes conn explicitly (runs
from the Celery sweep and from a Huume tool)."""

async def check_incident_against_handbook(conn, *, company_id: UUID, incident: dict) -> dict:
    # incident needs: id, title, description, incident_type, severity, occurred_at.
    # Returns {"violations": [PolicyViolationMatch-shaped dicts], "citations": evidence_map,
    #          "dropped_citations": [...], "summary": str, "available": bool}. Never raises.
    # Grounding: hp.gather_grounding(conn, company_id, {"scopes": []}) → hp.build_corpus(grounding)
    #   (pure; precedent huume/handbook_skill.py:153-164) + the incident-side candidates from
    #   routes/ir_incidents/ai_analysis.py:_get_handbook_policy_entries(conn, company_id)
    #   (takes conn, directly reusable) + active `policies` rows.
    # Gemini: same envelope as discipline_ai.draft_discipline_letter — _genai().aio.models
    #   .generate_content under asyncio.wait_for; failure → {"available": False, ...}.
    # Citation gate: validate_citations(evidence_map, index) — bogus cids dropped, finding kept.

async def persist_policy_check(conn, *, incident_id, result: dict) -> None:
    # UPSERT ir_incident_analysis(analysis_type='policy_mapping') — same ON CONFLICT shape as
    # _auto_map_policy_violations (ai_analysis.py:952-987). MUST preserve the
    # PolicyMappingAnalysis reader contract (matches[]/summary/no_matching_policies/
    # generated_at/...) — get_policy_mapping (24h cache) + the IR analysis tab read it.
    # Adds keys, never renames: citations, dropped_citations, checked_by='discipline_policy_check'.
```

Retaliation note (in module docstring + test): `discipline_compliance._fetch_protected_activity`
already reads `ir_incidents` by `reported_by_email` as a protected-activity signal — the skill
passes real `occurrence_dates` (incident `occurred_at`) so that gate and the sick-leave block
evaluate true dates. Self-reported-injury discipline surfaces the retaliation advisory unchanged.

---

## 4. Engine changes — `server/app/matcha/services/discipline/discipline_engine.py`

**4a. `issue_discipline_with_supersede`** gains 3 keyword params (signature `:359-385`, INSERT
`:407-424`, `RECORD_COLUMNS` `:92-103` all extended; bootstrap CREATE matches):

```python
async def issue_discipline_with_supersede(
    *, ...existing 18 params...,
    approval_status: str = "not_required",            # 'not_required' | 'pending'
    source_incident_id: Optional[UUID] = None,
    template_id: Optional[UUID] = None,
) -> dict[str, Any]:
    # GAP-2 enforcement lives IN THE ENGINE so no caller can get it wrong:
    #   if approval_status == "pending" and remedial_requirement_id is not None:
    #       pending_remedial_requirement_id = remedial_requirement_id
    #       remedial_requirement_id = None        # nothing assigned until approval
    # approval_requested_at = NOW() when approval_status == 'pending'.
```

**4b. `transition_status`** (`:518-573`) — the GAP-1 choke point. One WHERE-clause change guards
all 6 callsites at once; approved and legacy (`not_required`) records pass unchanged:

```sql
UPDATE progressive_discipline SET ...
WHERE id = $1 AND status = ANY($2)
  AND COALESCE(approval_status, 'not_required') NOT IN ('pending', 'denied')
```
Returns `None` → existing callers already 409. Docstring states the invariant: *no status
transition may advance a record whose approval is pending or denied.*

**4c. New approval state machine** (engine-level so routes and the Huume skill share one
implementation; callers own notification dispatch):

```python
async def approve_record(conn, *, discipline_id: UUID, company_id: UUID,
                         actor_user_id: UUID) -> Optional[dict[str, Any]]:
    """ONE transaction: flip approval (guarded UPDATE ... WHERE approval_status='pending'
    AND company_id=$2, RETURNING — None on wrong state/tenant) → assign
    pending_remedial_requirement_id via _assign_training(source_type='discipline',
    source_ref=id) and copy it into remedial_requirement_id → transition_status
    (draft → pending_meeting; passes the 4b guard because approval_status is now
    'approved') → write_audit('approval_approved') + write_audit('issued').
    Approval IS the issue step. Returns the transitioned record."""

async def deny_record(conn, *, discipline_id: UUID, company_id: UUID,
                      actor_user_id: UUID, reason: str) -> Optional[dict[str, Any]]:
    """ONE transaction, direct guarded UPDATE (NOT transition_status — the 4b guard
    correctly refuses everything else once denied):
      SET approval_status='denied', status='denied', denial_reason=$r,
          approved_by=$actor, approval_decided_at=NOW()
      WHERE id=$1 AND company_id=$2 AND approval_status='pending' RETURNING <RECORD_COLUMNS>
    + write_audit('approval_denied', {'reason': reason}). Terminal — no un-deny;
    changing course = a new record, so the trail shows both decisions."""

async def list_pending_approval(conn, company_id: UUID) -> list[dict[str, Any]]
```
`write_audit.action` is free VARCHAR(40) (no CHECK) — new names fine.
`list_records_for_company(conn, company_id, status_filter=...)` (`:671`) gains
`approval_filter: Optional[str] = None`.

---

## 5. Routes — `server/app/matcha/routes/employee_lifecycle/discipline.py`

New Pydantic models (beside the existing ones at `:42-91`):

```python
class DenyRequest(BaseModel):
    # ≥20 mirrors the only existing long-reason floor, override_reason
    # (discipline_engine.py:390-391) — NOT RefuseRequest (min_length=1).
    reason: str = Field(..., min_length=20)

class TemplateUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    infraction_type: Optional[str] = None
    discipline_type: Optional[str] = Field(None, pattern="^(verbal_warning|written_warning|pip|final_warning|suspension)$")
    body: str = Field(..., min_length=20)
    is_default: bool = False
    is_active: bool = True

class ApproverToggleRequest(BaseModel):
    is_hr_approver: bool
```

New routes — **`GET /records/pending-approval` MUST be declared above
`GET /records/{discipline_id}` (currently `:405`)** or the path param swallows it:

| Route | Behavior |
|---|---|
| `GET /records/pending-approval` | `discipline_engine.list_pending_approval`; serialized list. |
| `POST /records/{discipline_id}/approve` | `_ensure_record_in_company` → `approve_record(...)`; `None` → 409 `"Record is not awaiting approval"`. Then best-effort `dispatch(record=..., action="discipline_approved", audience="manager_only", skip_user_id=current_user.id)` in try/except (same posture as the POST /records tail `:357-372`). |
| `POST /records/{discipline_id}/deny` | body `DenyRequest` → `deny_record(...)`; `None` → 409. Dispatch `discipline_denied`, `audience="hr_only"`. |
| `GET /templates` / `POST /templates` / `PUT /templates/{template_id}` / `DELETE /templates/{template_id}` | thin wrappers over `discipline_templates.*`; DELETE = `deactivate_template` (soft). |
| `GET /approvers` | client users of the company (`clients JOIN users`) + `is_hr_approver`. |
| `PUT /approvers/{user_id}` | body `ApproverToggleRequest`; UPDATE `clients` row guarded `WHERE user_id=$1 AND company_id=$2` (404 on 0 rows). Lives here (not a team page) — approvers are a discipline setting; UI lands on DisciplineSettings. |

`GET /records` (`:390`) gains `approval_status: Optional[str] = None` → passed to
`list_records_for_company(..., approval_filter=...)`.

`POST /records` (direct-issue path) is **unchanged** — engine default keeps
`approval_status='not_required'` and the existing tail (`:347-373`) still runs. There is no
`_issue_tail` extraction: the transactional state machine now lives in the engine
(`approve_record`), and the two paths' dispatches differ by design (`discipline_issued` vs
`discipline_approved`) — a shared tail would have to parameterize everything it does.

Signature-completion filing (GAP 3/4): both PDF-landing paths —
`upload-physical` (`:574-628`, after `signed_pdf_storage_path` is written) and the webhook
completed branch (`:704-737`) — call the new filing hook (§6) best-effort.

---

## 6. `server/app/matcha/services/discipline/discipline_filing.py` (NEW)

```python
"""Post-signature filing of the signed letter. Never raises — filing must not
fail a signature write that already committed (log-and-continue)."""

def signed_letter_doc_type(discipline_id: UUID) -> str:
    return f"discipline:{discipline_id}"   # 47 chars, fits VARCHAR(50).
    # GAP-3: employee_documents has partial-unique (employee_id, doc_type) WHERE status IN
    # ('pending_signature','signed') — a literal 'disciplinary_action' collides on the 2nd
    # letter. Embedding the record id (the handbook:<id>:<version> convention) makes each
    # letter its own doc AND makes webhook redelivery naturally idempotent.

async def file_signed_letter(conn, record: dict[str, Any]) -> None:
    # 1. employee_documents row — NOTE tenant col is org_id, not company_id:
    #    INSERT (org_id, employee_id, doc_type, title, storage_path, status, signed_at)
    #    VALUES ($company, $emp, signed_letter_doc_type(id),
    #            'Disciplinary action — <discipline_type> (<issued_date>)',
    #            record['signed_pdf_storage_path'], 'signed', record['signature_completed_at'])
    #    ON CONFLICT (employee_id, doc_type) WHERE status IN ('pending_signature','signed')
    #    DO NOTHING            -- same conflict target handbook_service uses (:2317-2323)
    # 2. When record['source_incident_id']: ir_incident_documents row,
    #    document_type='disciplinary', file_path = the same storage path, guarded by
    #    WHERE NOT EXISTS (SELECT 1 ... WHERE incident_id=$1 AND file_path=$2)
    #    (table has no unique). Renders on the incident's existing Documents tab.
```

Portal renders the employee_documents row via the generic non-handbook branch (needs
`storage_path` — set). Admin surface: deferred (decision #2); DisciplineDetail already links the
signed PDF (`DisciplineDetail.tsx:162-171`).

---

## 7. Notifications — `server/app/matcha/services/discipline/discipline_notifications.py`

```python
_TITLES gains (dispatch early-returns on unknown actions — these are mandatory):
    "discipline_approval_requested": "Discipline Approval Requested",
    "discipline_approved": "Discipline Approved",
    "discipline_denied": "Discipline Denied",

async def dispatch(*, record, action, notify_grandparent: bool = True,
                   skip_user_id: Optional[UUID] = None,
                   audience: str = "all") -> None:
    # audience ∈ {"all", "hr_only", "manager_only"}; recipient resolution stays inline:
    #  "all"          → today's set exactly (manager CTE + optional grandparent + issuer + all
    #                   active client users) — existing 5 actions untouched.
    #  "hr_only"      → designated approvers (clients.is_hr_approver = TRUE) — falls back to
    #                   ALL active client users when a company has designated nobody, so the
    #                   queue never dead-ends. NO manager: the manager must not learn of a
    #                   draft that may be denied.
    #  "manager_only" → manager chain (+grandparent per flag); when NO manager resolves
    #                   (manager_id sparse — only bulk upload sets it today, and the users
    #                   lookup silently drops unresolvables) → fall back to the hr_only set,
    #                   or an approved letter notifies nobody.
```

---

## 8. Worker — `server/app/workers/tasks/discipline_policy_sweep.py` (NEW)

No queue table, no request-path hook — **zero code at the two incident-close sites**. Modeled
directly on `hr_proactive_push.py` (source-table scan + SQL `NOT EXISTS` ledger + one
transaction per delivery + `_AlreadyStamped` rollback trip-wire `:324-384` + scheduler gate
`:571-579`).

```python
@celery_app.task(name="discipline_policy_sweep")
def discipline_policy_sweep(): ...  # asyncio.run(_run()) — worker is pool-free

async def _run() -> dict:
    # 1. Gate: scheduler_settings row 'discipline_policy_sweep' (absent/disabled → skipped);
    #    limit = max_per_cycle or 25. Limit counts THREADS OPENED, not rows scanned.
    # 2. Scan (SQL prefilter, then merge_company_features re-check in Python — huume is
    #    admin-toggle-only, not in any tier overlay, but merge is the rule):
    #    SELECT i.id, i.company_id, i.title, i.incident_number, i.description,
    #           i.incident_type, i.severity, i.occurred_at
    #    FROM ir_incidents i JOIN companies c ON c.id = i.company_id
    #    WHERE i.status = 'closed' AND i.updated_at > NOW() - INTERVAL '14 days'
    #      AND (c.enabled_features->>'huume')::boolean IS TRUE
    #      AND NOT EXISTS (SELECT 1 FROM discipline_policy_sweep_log l WHERE l.incident_id = i.id)
    #    ORDER BY i.updated_at LIMIT $scan_cap
    #    Python re-check per company: merged features require huume+matcha_work+discipline+incidents.
    # 3. Per incident (each failure logged-and-skipped, per-event isolation):
    #    result = check_incident_against_handbook(conn, ...); persist_policy_check(conn, ...)
    #    - no violations (or available=False after retry-worthy? available=False → SKIP, no
    #      stamp — a Gemini outage must not permanently mark incidents "checked") →
    #      violations==[] and available=True → stamp ledger (thread_id NULL, finding_count 0).
    #    - violations → _open_thread(...) in ONE transaction:
    #        INSERT mw_threads (company_id, created_by, title, current_state, huume_mode)
    #          VALUES ($1,$2,$3,'{}'::jsonb, true) RETURNING id
    #        INSERT mw_messages (thread_id, 'assistant', $briefing, metadata
    #          {'source':'discipline_policy_sweep','incident_id':...})   -- DETERMINISTIC
    #          template over the stored check result (violation titles + citation counts +
    #          "reply here to draft a disciplinary action — I'll route it for HR approval").
    #          NO Gemini in the briefing; the grounded turn happens when the admin replies.
    #        INSERT mw_notifications (type='hr_proactive', link=f'/work/{thread_id}') for the
    #          recipient set (hr_only resolution: designated approvers else all clients)
    #        INSERT discipline_policy_sweep_log ... ON CONFLICT (incident_id) DO NOTHING
    #          RETURNING id; None → raise _AlreadyStamped → whole unit rolls back.
    #    created_by = oldest active client user (copy _company_client_users, hr_proactive_push:267-287).
```

`celery_app.py`: register the task in the `@worker_ready` periodic dispatch list.

---

## 9. Huume — tools / actions / agent / skill / record_view / prompt

### 9a. `services/huume/tools.py`
```python
SHOW_RECORD_TYPES = ("incident", "er_case", "employee", "credential", "discipline")

_tool("check_incident_policy", "read",
    "Check a closed incident's narrative against the company's handbook and policies. "
    "Returns candidate policy violations with citations. Read-only; reports, never decides.",
    properties={"incident_id": {"type": "string"}}, required=["incident_id"])
_tool("draft_disciplinary_action", "staged",
    "Stage a disciplinary action from an incident (or standalone). Takes IDS, never names — "
    "use lookup_context first. Routes to HR for approval; nothing is issued until approved.",
    properties={"employee_id": str, "incident_id": str?, "infraction_type": str,
                "severity": str?, "discipline_type": str?, "occurrence_dates": ARRAY[str]?,
                "description": str, "expected_improvement": str?, "template_id": str?,
                "confirm_id": str?},
    required=["employee_id", "infraction_type", "description"])
_tool("decide_disciplinary_action", "staged",
    "Approve or deny a discipline record that is pending HR approval. Denial requires a "
    "written reason (recorded on the legal record).",
    properties={"record_id": str, "decision": enum["approve","deny"], "reason": str?},
    required=["record_id", "decision"])
_tool("list_pending_approvals", "read",
    "List this company's discipline records awaiting HR approval, with ids.")
```

### 9b. `services/huume/actions.py`
```python
_HUUME_ACTION_REQUIRED_FEATURE gains:      # absent type = refused at :145-147, so this IS the gate
    "discipline_from_incident": "discipline",
    "discipline_decision": "discipline",
_DISCIPLINE_SKILL_ACTIONS = frozenset({"discipline_from_incident", "discipline_decision"})

# evaluate_huume_action confirm-turn branches (beside discipline_draft's at :178-199):
def _validate_discipline_from_incident(staged: dict) -> HuumeVerdict:
    # employee_id parses as UUID; infraction_type non-empty; severity ∈
    # {minor,moderate,severe,immediate_written} when given; discipline_type ∈ the 5-value vocab
    # when given; occurrence_dates all ISO dates; description non-empty.
    # HARD-STOP RE-CHECK: classify_message over description+expected_improvement — this IS a
    # discipline write-up (same rule as discipline_draft), NOT an incident narrative
    # (the _validate_ir_report asymmetry at :257-265 does not apply).
def _validate_discipline_decision(staged: dict) -> HuumeVerdict:
    # record_id parses as UUID; decision ∈ {approve, deny};
    # deny requires reason with len(reason.strip()) >= 20 (mirrors DenyRequest).

# execute_huume_action gains:
    if action.get("type") in _DISCIPLINE_SKILL_ACTIONS:
        from app.matcha.services.huume import discipline_skill
        return await discipline_skill.execute(company_id=company_id,
                                              actor_user_id=actor_user_id, action=action)
```

### 9c. `services/huume/discipline_skill.py` (NEW — one file per skill, matching siblings)
```python
"""Huume incident→discipline skill. Executors return the standard
{status, message, record_id?, record_label?, bg_tasks?} shape
(hr_pilot_actions.py:578-582); bg_tasks carry the notification dispatch so it
runs post-commit, same contract as the agent's existing drain."""

async def check_incident_policy(*, company_id: UUID, incident_id: str) -> dict
    # Company-scoped incident load (404→{"status":"not_found"}); requires the company's
    # `handbooks` feature for the corpus (module-off note otherwise, three-state idiom);
    # runs §3 check + persist. Model-safe return: violation titles + policy ids + citation
    # count + summary — NEVER involved_employee_ids / names (legal-record rule).

async def stage_enrichment(conn, *, company_id: UUID, staged: dict) -> dict
    # At STAGE time: resolve_template(list_templates(...), ...) → render_template with
    # build_placeholder_values → adds template_name/template_id, rendered body preview,
    # missing_fields ("no manager on file — the letter will say 'your manager'"),
    # and the latest policy-check citations for the incident (if any). Enriches the
    # staged dict the panel renders; nothing is written.

async def execute(*, company_id: UUID, actor_user_id: Optional[UUID], action: dict) -> dict
    # type == "discipline_from_incident":
    #   1. check_discipline_compliance FIRST (blocked → {"status":"blocked", message}) —
    #      same order as hr_pilot_actions._execute_discipline_draft (:609-638).
    #   2. occurrence_dates: staged list, else [incident.occurred_at.date()] when
    #      source_incident_id set — real dates so the leave-overlap + retaliation
    #      signals evaluate truthfully.
    #   3. issue_discipline_with_supersede(..., approval_status="pending",
    #      source_incident_id=..., template_id=..., compliance_check=verdict)
    #   4. bg_tasks = [(discipline_notifications.dispatch, (), {"record": row,
    #      "action": "discipline_approval_requested", "audience": "hr_only"})]
    #   → {"status": "created", "record_id": str(row["id"]),
    #      "record_label": f"Disciplinary action ({row['discipline_type']}) — pending HR approval"}
    # type == "discipline_decision":
    #   approve → discipline_engine.approve_record(...); None → {"status":"error",
    #     "message":"That record isn't awaiting approval."};
    #     bg_tasks dispatch discipline_approved audience=manager_only.
    #   deny → deny_record(..., reason=...); bg_tasks dispatch discipline_denied audience=hr_only.

async def list_pending(*, company_id: UUID) -> dict   # ids + labels for the read tool
```

### 9d. `services/huume/agent.py`
- `check_incident_policy` + `list_pending_approvals`: plain read arms (pattern:
  `check_offer_status` arm at `:440-443`).
- `draft_disciplinary_action`: bespoke staged arm cloned from `draft_discipline` (`:468-519`) —
  mints `uuid4().hex[:8]` confirm_id, staged type `"discipline_from_incident"`, calls
  `stage_enrichment` before writing `state_updates["huume_action"]`, drains `bg_tasks`
  best-effort after execute (same loop as `:509-514`).
- `decide_disciplinary_action`: **one new `_HR_OPS_TOOL_SPECS` entry** — the table arm
  (`:521-557`) handles it generically:
  ```python
  "decide_disciplinary_action": {
      "action_type": "discipline_decision", "match_key": "record_id",
      "mints_confirm_id": False, "fields": ("record_id", "decision", "reason"),
      "staged_label": "Staged: discipline approval decision",
      "refused_label": "Discipline decision refused",
      "done_label": "Discipline decision recorded",
      "failed_label": "Discipline decision not recorded",
      "done_status": "decided",
  }
  ```
  (Execute routes through `execute_huume_action` → `_DISCIPLINE_SKILL_ACTIONS` branch — the
  table arm's `status == "created"` check governs done/failed, so `execute` returns
  `"created"` on success for both decisions.)
- `cancel_staged` message switch (`:606-611`) gains:
  `discipline_from_incident` → "Cancelled — that disciplinary action will not be filed." ;
  `discipline_decision` → "Cancelled — no approval decision was recorded."

### 9e. `services/huume/record_view.py`
Docstring checklist (`:17-19`) — four registries + two builders; two parity tests enforce:
```python
RECORD_REQUIRED_FEATURE["discipline"] = "discipline"

async def _model_discipline(conn, company_id: UUID, rid: UUID) -> Optional[dict]:
    # NAME-FREE (legal record): id, discipline_type, infraction_type, severity, status,
    # approval_status, issued_date, review_date. No employee name, no description.
async def _build_discipline_view(conn, company_id: UUID, rid: UUID) -> Optional[dict]:
    # Panel view (admin's own auth): JOIN employees for the name; chips = status +
    # approval_status + severity; sections = description / expected_improvement /
    # occurrence dates / denial_reason when present; link '/app/discipline'.
_MODEL_BUILDERS["discipline"] / _VIEW_BUILDERS["discipline"]
```

### 9f. `services/huume/prompt.py`
- `build_state_block` is a **per-type switch** (`:29-60`) — add two branches:
  `discipline_from_incident` (echo confirm_id + employee/infraction + "files it FOR HR
  APPROVAL — nothing is issued until an approver decides") and `discipline_decision`
  (echo record_id + decision).
- `build_system_prompt` gains `## Incident-triggered discipline` after the existing
  "## Discipline write-ups" section: check_incident_policy first; draft with ids from
  lookup_context; template auto-resolution is server-side; two-turn stage/confirm; the draft
  goes to HR approval, not straight to issuance; denial needs a written reason ≥20 chars;
  use show_record to open a discipline record in the panel instead of retyping it.

### 9g. Route + `onboarding_skill.py`
- `routes/matcha_work/huume.py` needs **no change** — the GET record route reads
  `RECORD_REQUIRED_FEATURE` dynamically (`:171-177`).
- `onboarding_skill.py:462-483` `discipline` topic: extend the counts query to also return
  pending-approval records **with ids** (`id, discipline_type, infraction_type,
  approval_requested_at` — the decision tool takes ids, never names; counts stay name-free).

---

## 10. Frontend

### 10a. Types — `client/src/work/types.ts` (union at `:610-617`)
```ts
export interface HuumeActionDisciplineFromIncident {
  type: 'discipline_from_incident'
  status: 'proposed' | 'filed' | 'failed' | 'cancelled'
  confirm_id: string
  employee_id: string
  employee_name?: string           // enrichment adds it for display; executor uses the id
  incident_id?: string
  infraction_type: string
  severity?: string
  discipline_type?: string
  occurrence_dates?: string[]
  description?: string
  expected_improvement?: string
  template_id?: string
  template_name?: string
  rendered_preview?: string
  missing_fields?: string[]
}
export interface HuumeActionDisciplineDecision {
  type: 'discipline_decision'
  status: 'proposed' | 'decided' | 'failed' | 'cancelled'
  record_id: string
  decision: 'approve' | 'deny'
  reason?: string
}
// both appended to the HuumeAction union
```

### 10b. Per-type UI sites (all five — the review found the plan missed three of these)
- `utils/huumeActionMeta.tsx` — `DONE_LABELS`:
  `discipline_from_incident: { filed: 'Disciplinary action staged for HR approval' }`,
  `discipline_decision: { decided: 'Approval decision recorded' }`; `bannerLabel` cases
  (`Stage disciplinary action for ${employee_name ?? 'employee'} — confirm?`,
  `${decision === 'deny' ? 'Deny' : 'Approve'} this disciplinary action?`); `actionIcon`:
  `discipline_decision` → `<Gavel/>`; `discipline_from_incident` falls through to the existing
  `<ShieldAlert/>` default.
- `components/panels/HuumePanel/ConfirmBar.tsx:14-21` — id switch:
  `discipline_from_incident` → `confirm_id`; `discipline_decision` → `record_id`.
- `components/panels/HuumePanel/ActionDocViewer.tsx` — title cases ('Disciplinary action',
  'Approval decision') + one body block each (from-incident: employee/infraction/level/
  occurrence dates/description/expected_improvement/template chip/missing_fields warning;
  decision: record id + decision + reason).
- `HuumeActionCard.tsx` — generic over `DONE_LABELS`/`actionIcon`, no change.
- `HuumePanel/RecordViewer.tsx` — type-generic, no change (new `discipline` record type is
  backend-only).

### 10c. Discipline app surfaces
- `api/discipline/discipline.ts` (`disciplineApi` at `:199`) — add:
  `approve(id)`, `deny(id, reason)`, `pendingApprovals()`, `listTemplates()`,
  `upsertTemplate(body, id?)`, `deleteTemplate(id)`, `listApprovers()`,
  `setApprover(userId, isApprover)`; `list(status?, approvalStatus?)` gains the param.
- `hooks/discipline/useDiscipline.ts` — extend `useDisciplineList(status, approvalStatus?)`;
  add `useDisciplineTemplates()`, `useDisciplineApprovers()`.
- `pages/app/discipline/Discipline.tsx` — **no tabs exist** (flat table + server-side status
  `Select` at `:118-140`): add options `Pending approval` (sends `approval_status=pending`),
  `Denied`, `Draft` (currently missing); `STATUS_LABEL` gains `denied`. Approval chip column
  when `approval_status !== 'not_required'`.
- `pages/app/discipline/DisciplineDetail.tsx` — approval banner: `pending` → Approve button +
  Deny-with-reason (client-side ≥20 mirror; server enforces regardless); `denied` → terminal
  banner with `denial_reason`; `approved` → chip with approver + date.
- `pages/app/discipline/DisciplineSettings.tsx` — two new sections beside policy mapping:
  **Letter templates** (list + editor: name, infraction_type select, discipline_type select,
  body textarea with a placeholder legend rendering `DISCIPLINE_TEMPLATE_PLACEHOLDERS`, default
  toggle) and **HR approvers** (client-user list + `is_hr_approver` toggles, with the fallback
  rule stated: "no approvers designated = every business admin is asked").
- `components/ir/IRDocumentPanel.tsx:7-10` — `DOC_TYPE_OPTIONS` gains
  `{ value: 'disciplinary', label: 'Disciplinary' }` (badge renders raw string otherwise).

---

## 11. Tests

All new backend tests use the repo's mock-conn idiom (`_conn_ctx` MagicMock, see
`tests/huume/test_huume_store.py`) — no live DB. **Patch the module that DEFINES the caller,
never a facade** (server/CLAUDE.md rule).

`server/tests/discipline/test_discipline_templates.py` (pure, DB-free):
- `test_resolve_exact_match_wins` — exact (infraction, level) beats infraction-only and default.
- `test_resolve_falls_back_to_infraction_only`, `test_resolve_falls_back_to_default`,
  `test_resolve_none_when_no_match` (→ draft from scratch), `test_resolve_ignores_inactive`.
- `test_render_replaces_known_placeholders`, `test_render_leaves_unknown_placeholders_verbatim`
  (`{{typo_token}}` survives literally), `test_render_reports_missing_fields_for_empty_values`
  (manager_name=None → rendered '' + listed in missing_fields).
- `test_placeholder_vocabulary_is_closed` — a body containing every documented token renders
  with zero missing when all values supplied; regex matches nothing else.

`server/tests/discipline/test_discipline_approval.py`:
- `test_engine_defers_remedial_when_approval_pending` — issue with `approval_status='pending'`
  + remedial id: INSERT args carry pending_remedial, remedial None, `_assign_training` NOT
  called (GAP 2).
- `test_engine_assigns_remedial_immediately_when_not_required` — pins today's behavior.
- `test_transition_status_sql_guards_approval` — the UPDATE SQL contains the
  `COALESCE(approval_status,...)` guard (GAP 1 pinned at the choke point).
- `test_approve_only_from_pending` / `test_deny_only_from_pending` — 0-row UPDATE → None.
- `test_deny_is_terminal` — after deny, `transition_status` returns None for every `to`.
- `test_direct_issue_defaults_not_required` — no approval args → `'not_required'` in INSERT.
- Route-level: `test_deny_request_requires_20_chars` (pydantic), and
  `test_pending_approval_route_declared_before_id_route` — assert via
  `[r.path for r in router.routes]` ordering (the FastAPI path-swallow gotcha).

`server/tests/discipline/test_discipline_policy_check.py` (fake Gemini):
- `test_reports_never_adjudicates` — output schema has no level/legality key.
- `test_citation_gate_drops_unknown_ids` — bogus cid dropped, finding kept.
- `test_persist_preserves_policy_mapping_reader_contract` — persisted JSON keeps
  matches/summary/no_matching_policies/generated_at.
- `test_gemini_failure_degrades_available_false` (never raises).

`server/tests/discipline/test_discipline_filing.py`:
- `test_doc_type_embeds_record_id_and_fits_varchar50`.
- `test_filing_idempotent_on_redelivery` — second call inserts nothing (conflict/NOT EXISTS).
- `test_incident_row_only_when_source_incident_set`, `test_filing_never_raises`.

`server/tests/discipline/test_discipline_notifications_audience.py`:
- `test_new_titles_registered` (3 keys), `test_hr_only_targets_designated_approvers`,
  `test_hr_only_falls_back_to_all_clients_when_none_designated`,
  `test_hr_only_never_includes_manager`,
  `test_manager_only_falls_back_to_hr_when_no_manager_resolves`,
  `test_default_audience_unchanged`.

`server/tests/huume/test_huume_discipline_skill.py`:
- `test_both_action_types_in_required_feature_registry` (→ `"discipline"`).
- `test_stage_then_confirm_is_two_turns` (`this_turn_staged_new=True` → stage verdict).
- `test_hard_stop_reruns_on_confirm` (harassment text in description → refuse).
- `test_decision_deny_without_reason_refused` / `test_decision_deny_short_reason_refused`.
- `test_decision_validates_record_id_uuid`, `test_execute_routes_to_discipline_skill`.
- `test_stage_uses_incident_occurred_at_for_occurrence_dates` (retaliation/leave gates get
  real dates).
- `test_model_discipline_view_is_name_free` (no employee name/description keys).
- `_HR_OPS_TOOL_SPECS` entry: `test_decide_tool_spec_match_key_is_record_id`.
- Existing parity tests (`test_huume_record_view.py:80-87`,
  `test_huume_lookups.py:176-185`) — updated expectations cover the fifth type automatically.

`server/tests/workers/test_discipline_policy_sweep.py`:
- `test_skips_when_scheduler_disabled`, `test_scan_sql_has_not_exists_ledger`,
- `test_clean_incident_stamps_ledger_without_thread`,
- `test_gemini_unavailable_does_not_stamp` (outage ≠ checked),
- `test_thread_open_is_single_transaction_with_stamp` (rollback on `_AlreadyStamped`).

Frontend: `npx tsc -p tsconfig.app.json --noEmit` (the bare `npx tsc --noEmit` checks nothing).

---

## 12. Docs (same PR)

- Root `CLAUDE.md` `huume` flag row: incident→discipline skill (4 tools, approval semantics,
  the sweep) appended; Key Modules **Discipline** bullet gains the approval state machine +
  templates + policy check + filing.
- `server/app/matcha/routes/CLAUDE.md`: `employee_lifecycle/discipline.py` row mentions
  approval/templates/approvers routes.
- No new feature flag — rides `discipline` + `huume` + `matcha_work` + `incidents` (+
  `handbooks` for the corpus).

---

## 13. Verification

```bash
cd server && ./venv/bin/python -m pytest tests/discipline/ tests/huume/ tests/workers/ -q
cd client && npx tsc -p tsconfig.app.json --noEmit
# migration (dev only; prod needs explicit approval per repo safety rules):
MIGRATE_REHEARSAL=1 ... alembic upgrade heads    # rehearse first
./scripts/migrate-dev.sh
```

Manual E2E on dev (`dev-remote.sh` already on :5174 — never pkill by port pattern):
1. DisciplineSettings → create a template (default) + designate one HR approver.
2. File + close an incident whose narrative breaches a handbook policy; enable the
   `discipline_policy_sweep` scheduler row; fire the task → pre-briefed Huume thread opens,
   briefing cites the stored finding; second run opens nothing (ledger).
3. In the thread: `check_incident_policy` → `draft_disciplinary_action` (stage shows template
   + missing_fields) → confirm → record exists `status='draft'`, `approval_status='pending'`;
   designated approver got the notification, the manager did **not**.
4. Bypass check: `PATCH .../meeting-held` on that record → **409**.
5. Approve (page or `decide_disciplinary_action`) → `pending_meeting`, manager notified,
   remedial (if staged) now assigned. Deny path on a second record → terminal `denied` +
   reason; no training rows.
6. Meeting-held → signature → upload physical PDF → employee_documents row
   (`discipline:<id>`) + incident Documents tab shows 'disciplinary'; re-fire webhook → no
   duplicate rows.
7. `show_record` with the discipline id → opens in the panel, name-free model summary.

---

## 14. Completeness audit → rating 0.96

Checked against: 4 blocking gaps (all closed: GAP 1 §4b, GAP 2 §1/§4a/§4c, GAP 3 §6,
GAP 4 §1/§6/§10c) · both user decisions honored (§1 no.4 + §5 approvers routes + §10c;
deferred admin tab noted §6) · every touched layer enumerated with signatures (migration,
bootstrap ×4, engine, routes, 2 new services + filing, notifications, worker, celery
registration, 6 Huume files, 9 frontend files, docs) · both parity-test registries · route
declaration-order gotcha · state-block per-type switch verified and covered · pool-free +
never-raise postures stated where they're load-bearing · idempotency on both filing writes ·
test list names 40+ cases incl. every gap regression. Remaining 0.04: (a) the two dropped
CHECK-constraint names assume PG default naming — the migration uses IF EXISTS and the
rehearsal gate catches a mismatch, but verify on dev; (b) Gemini prompt wording for the policy
check will need a tuning pass against a real incident; (c) DisciplineDetail/Settings JSX is
specified functionally, not to the component line. None changes the architecture.
