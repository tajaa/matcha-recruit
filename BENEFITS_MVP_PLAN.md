# Employee Benefits MVP — full open-enrollment workflow

## Context

Matcha's existing `benefits_admin` feature is a broker-adjacent eligibility/risk tool: a mutable roster snapshot (`benefit_roster_entries`, Finch/CSV ingest) feeding an exception detector (new-hire enrollment gaps, termination premium leaks) and renewal-risk bands. There is no real benefits administration — no plan catalog, no enrollment, no employee elections, and no client UI at all (`productNavCatalog.ts:60` points `benefits_admin` at `/app/employees` as a placeholder).

This adds a full open-enrollment system **under the same `benefits_admin` flag** (user decision — no new flag; admin-toggleable for any tier): plan catalog + coverage tiers, open-enrollment periods, employee self-service elections (incl. waive) via the portal, life-event qualifying changes, and email reminders. New durable tables FK `employees.id` (canonical identity) — never the roster rows, which are fully overwritten each sync. The existing eligibility detector gains approved elections as a second enrollment-truth source.

## Step 1 — Alembic migration `benefitoe01_add_benefit_enrollment.py`

`server/alembic/versions/`, `down_revision` = current head (`alembic heads` at implementation time). Style of `benefitelig01`: `op.execute` raw DDL, `IF NOT EXISTS`, real `downgrade()` (drop reverse order + delete scheduler row). Commit before applying; user runs `./scripts/migrate-dev.sh` — never auto-run.

Tables:

- **`benefit_plans`** — `id UUID PK`, `company_id FK companies CASCADE`, `plan_type VARCHAR(30)` ('medical','dental','vision','life','disability','other'), `name`, `carrier_name`, `description`, `status VARCHAR(16) DEFAULT 'active'` ('draft','active','archived'), `waivable BOOL DEFAULT true`, `metadata JSONB`, timestamps. `UNIQUE(company_id, plan_type, name)`; index `(company_id, status)`.
- **`benefit_plan_tiers`** — `id`, `plan_id FK benefit_plans CASCADE`, `coverage_tier` CHECK in ('employee_only','employee_spouse','employee_children','family'), `employee_cost NUMERIC(12,2)`, `employer_cost NUMERIC(12,2)`, `cost_period VARCHAR(16) DEFAULT 'monthly'` ('monthly','per_pay_period'), timestamps. `UNIQUE(plan_id, coverage_tier)`.
- **`open_enrollment_periods`** — `id`, `company_id FK CASCADE`, `name`, `starts_on DATE`, `ends_on DATE` (CHECK `ends_on >= starts_on`), `plan_year_start DATE` (coverage effective; feeds `policy_month`), `status VARCHAR(16) DEFAULT 'draft'` ('draft','open','closed'), `opened_at`, `closed_at`, timestamps. **Partial unique index `ON (company_id) WHERE status='open'`** — at most one open period per company. Index `(company_id, status)`.
- **`life_event_changes`** — `id`, `company_id FK CASCADE`, `employee_id FK employees CASCADE`, `event_type VARCHAR(40)` (marriage/divorce/birth_adoption/death_of_dependent/loss_of_coverage/gain_of_coverage/dependent_status_change/relocation/other), `event_date DATE`, `description`, `status DEFAULT 'pending'` ('pending','approved','denied','expired'), `window_days INT DEFAULT 30`, `window_ends_on DATE` (set on approval: `GREATEST(event_date, CURRENT_DATE) + window_days`), `reviewed_by FK users SET NULL`, `reviewed_at`, `review_note`, timestamps. Indexes `(company_id, status)`, `(employee_id)`.
- **`benefit_elections`** — the core. `id`, `company_id FK CASCADE`, `employee_id FK employees CASCADE`, `open_enrollment_period_id FK CASCADE NULL`, `life_event_id FK CASCADE NULL`, `plan_type VARCHAR(30)`, `plan_id FK benefit_plans RESTRICT NULL`, `tier_id FK benefit_plan_tiers RESTRICT NULL`, `waived BOOL DEFAULT false`, `dependents JSONB DEFAULT '[]'` (`[{name, relationship, dob}]`), `status DEFAULT 'draft'` ('draft','submitted','approved','rejected'), `submitted_at`, `decided_at`, `decided_by FK users SET NULL`, `decision_note`, `effective_date DATE`, timestamps.
  - `CHECK num_nonnulls(open_enrollment_period_id, life_event_id) = 1` — election belongs to exactly one window (OE period XOR approved life event).
  - `CHECK (waived AND plan_id IS NULL AND tier_id IS NULL) OR (NOT waived AND plan_id IS NOT NULL AND tier_id IS NOT NULL)` — waive is a first-class row.
  - **Two partial unique indexes** (plain UNIQUE useless over nullable FKs): `(employee_id, plan_type, open_enrollment_period_id) WHERE open_enrollment_period_id IS NOT NULL` and same for `life_event_id`. One election per employee × plan_type × window.
  - Lifecycle: draft → submitted → approved | rejected; rejected returns to draft on employee edit; draft delete is hard delete.
  - Indexes `(company_id, status)`, `(open_enrollment_period_id)`, `(employee_id)`.
- **`benefit_enrollment_notices`** — reminder dedupe ledger. `id`, `company_id FK CASCADE`, `open_enrollment_period_id FK CASCADE`, `employee_id FK CASCADE`, `notice_type VARCHAR(30)` ('window_opened','unsubmitted_nudge','closing_soon'), `sent_at`. `UNIQUE(open_enrollment_period_id, employee_id, notice_type)`.
- **`benefit_enrollment_audit`** — per-domain audit table (convention: `ir_audit_log`, `er_audit_log`). `id`, `company_id FK CASCADE`, `actor_user_id FK users SET NULL`, `actor_role`, `entity_type VARCHAR(30)` (plan/tier/oe_period/election/life_event), `entity_id UUID`, `action VARCHAR(40)`, `detail JSONB`, `created_at`. Index `(company_id, created_at DESC)`.
- **Seed**: `scheduler_settings` row `benefit_enrollment_notifications`, `enabled=false`, `max_per_cycle=500`, `ON CONFLICT DO NOTHING` (mirrors `benefitelig01`).

## Step 2 — Backend layout: split `benefits.py` into package

Convert now (5 routes → ~20, four concerns; `git mv` at 125 lines nearly free). Sanctioned pattern — package **replaces** same-named module (like `employees/`); the naming trap only bites grouping folders coexisting beside a module. No empty-path routes, so use the `matcha_work/` variant: fresh `APIRouter()` aggregator.

```
server/app/matcha/routes/benefits/
├── __init__.py      # router = APIRouter(); includes eligibility/plans/enrollment; exports `router`
├── eligibility.py   # git mv benefits.py here — 5 existing routes UNCHANGED (fix relative import depth)
├── plans.py         # plan + tier CRUD
└── enrollment.py    # OE periods, election review, life-event review
```

`routes/__init__.py:46` import + mount block at `:293` (`prefix="/benefits"`, `require_feature("benefits_admin")`) stay byte-identical.

- **New service** `server/app/matcha/services/benefits_enrollment.py` — do NOT stuff `benefits_eligibility.py`. Election upsert/submit/decide logic, `resolve_active_window(today, open_period_row, approved_life_events)`, `validate_election_payload(plan_row, tier_row, waived)`, `allowed_transition(current, action)` (pure, unit-testable), `log_benefit_audit(conn, ...)`, email subject/HTML builders.
- **New models** `server/app/matcha/models/benefits.py` — Pydantic v2, `Literal[...]`: `PlanCreate/PlanUpdate/TierInput`, `OePeriodCreate/Update`, `ElectionUpsert`, `DependentInput` (relationship `Literal['spouse','child','domestic_partner','other']`), `LifeEventCreate`, `DecisionInput`.

## Step 3 — Endpoints

Admin/client: `Depends(require_admin_or_client)` + `company_id = await get_client_company_id(current_user)`, `WHERE company_id=$1` everywhere. Gate at mount.

**plans.py** (under `/benefits`):
- `GET /plans` (nested tiers; `?status=` filter, default excludes archived) · `POST /plans` (plan+tiers one tx; audit) · `GET /plans/{id}` · `PATCH /plans/{id}` · `PUT /plans/{id}/tiers` (replace-set: upsert `ON CONFLICT (plan_id, coverage_tier)`, delete missing unless election-referenced → 409) · `DELETE /plans/{id}` (hard delete if zero elections, else archive; response says which).

**enrollment.py**:
- `GET/POST /enrollment/periods`, `PATCH /enrollment/periods/{id}` (draft-only edits; `ends_on` extension allowed while open)
- `POST /enrollment/periods/{id}/open` (draft→open; catch `UniqueViolationError` from partial index → 409 "another period already open") · `POST .../close`
- `GET /enrollment/periods/{id}/elections` — review dashboard: elections joined employees/plans/tiers + status counts + active employees with nothing submitted
- `POST /enrollment/elections/{id}/approve` (submitted→approved; stamp `decided_*`, `effective_date` = period `plan_year_start` else day after `ends_on`; life-event = `event_date`; audit) · `POST .../reject` (+note)
- `GET /enrollment/life-events` (`?status=pending` default) · `POST /enrollment/life-events/{id}/approve` (set `window_ends_on`) · `POST .../deny`

**Portal** — append to `server/app/matcha/routes/employee_portal.py`. Gate = exact `_schedule_dep` pattern (`employee_portal.py:653`): `_benefits_dep = [Depends(require_feature("benefits_admin"))]` per endpoint + `require_employee_record`; `require_feature` resolves employee → `org_id` company (verified). Company id = `employee["org_id"]`.
- `GET /me/benefits` — one payload: active window (open OE period covering today, else my approved life event with `window_ends_on >= today`), offered active plans+tiers, my elections in window, current approved coverage (latest approved per plan_type)
- `PUT /me/benefits/elections` — upsert one election in active window (`ON CONFLICT` on matching partial key). 409 no window; 409 if plan_type already submitted/approved this window; editing rejected resets to draft. Validate plan/tier ∈ `org_id`, tier ∈ plan, waive only if all active plans of type waivable
- `POST /me/benefits/elections/submit` — submit all my drafts in window at once; 400 if none
- `DELETE /me/benefits/elections/{id}` — own drafts only
- `GET /me/benefits/life-events` · `POST /me/benefits/life-events` (→ pending; audit)

## Step 4 — Eligibility-engine integration (`services/benefits_eligibility.py`)

Additive; CSV/Finch-only companies see zero change (empty set):
1. In `detect_eligibility_exceptions`, pre-fetch `SELECT DISTINCT employee_id FROM benefit_elections WHERE company_id=$1 AND status='approved'` — **waives included** (approved waive = addressed decision).
2. New-hire-gap branch (~L266): add `and e["employee_id"] not in addressed_ids`. Null `employee_id` roster rows keep current behavior.
3. `compute_renewal_risk`: fetch most relevant period (`ORDER BY status='open' DESC, plan_year_start DESC NULLS LAST LIMIT 1` — deterministic), compute `policy_month = ((today.month - plan_year_start.month) % 12) + 1`, thread through `_upsert_risk_dimension` into the existing (currently null) `benefit_renewal_risk.policy_month` column.

Leave `run_for_company`, ingestion, Finch `hris_deductions` write path untouched.

## Step 5 — Notifications worker

**New Celery task**, not a rider on `benefit_eligibility_sync` — that task also runs for broker-linked companies WITHOUT `benefits_admin` (worker query L31-40); enrollment emails must never fire there, and switches must be independent.

`server/app/workers/tasks/benefit_enrollment_notifications.py`, task gated by scheduler row from Step 1. Register in `celery_app.py`: `include` list + `on_worker_ready` dispatch block (copy existing pattern). Structure per `onboarding_reminders.py`: skip if disabled, honor `max_per_cycle`, per-company try/except. Companies filter: `enabled_features->>'benefits_admin'='true'` only.

Per cycle:
1. **Auto-transitions** (set-based single statements): draft→open when `starts_on <= today`; open→closed when `ends_on < today`; life events approved→expired when `window_ends_on < today`. Admin endpoints stay the manual override.
2. `window_opened` — active employees (email non-null, not terminated) anti-joined vs notices ledger.
3. `unsubmitted_nudge` — open ≥7 days, no submitted/approved election.
4. `closing_soon` — `ends_on - today <= 3`, no submitted/approved election.

Dedupe = claim-before-send: `INSERT INTO benefit_enrollment_notices ... ON CONFLICT DO NOTHING RETURNING id`; skip if no row; delete claim on send failure. Send via `get_email_service().send_email(...)` (reserved-domain guard built in). Builders in `services/benefits_enrollment.py`, link to `{frontend_url}/portal/benefits`. Enable post-deploy by flipping the scheduler row.

## Step 6 — Frontend (admin)

- **API** `client/src/api/benefits/benefits.ts` — all Step-3 admin endpoints PLUS the pre-existing `/benefits/eligibility-exceptions`, `/renewal-risk`, `/roster/*`, `/run` (first UI ever for those).
- **Page** `client/src/pages/app/benefits/Benefits.tsx` — single route, tabbed; tab components in `client/src/components/benefits/`:
  - `PlansTab.tsx` — plans table + modal editor with 4-row tier grid (`Select` takes `options[]`), archive.
  - `EnrollmentPeriodsTab.tsx` — list w/ status badge, create/edit modal, Open/Close (409 → `toast(msg,'error')`).
  - `ElectionsReviewTab.tsx` — period selector → elections table approve/reject (`Textarea` needs `label`), summary counts, not-yet-submitted list.
  - `LifeEventsTab.tsx` — pending queue, approve/deny.
  - `EligibilityTab.tsx` — existing exceptions + renewal-risk + roster CSV upload/template + Run button.
- **Wiring**: `AppRoutes.tsx` route `benefits` in `<FeatureGate feature="benefits_admin">`; `ClientSidebar.tsx` HR Ops group entry (`HeartPulse`, `/app/benefits`, feature `benefits_admin`); `productNavCatalog.ts:60` repoint `/app/employees` → `/app/benefits`.

## Step 7 — Frontend (portal)

- **API** `client/src/api/portal/portalBenefits.ts`.
- **Page** `client/src/pages/portal/PortalBenefits.tsx` — active-window banner (days remaining) or empty state + current coverage; per plan-type card: plan → tier (costs shown) → dependents editor rows → or Waive toggle; save = `PUT` per plan_type (draft badge); one "Submit elections" confirm modal → `POST .../submit`; life-event report form + status list.
- **Wiring**: `PortalRoutes.tsx` route in `<FeatureGate feature="benefits_admin" label="My Benefits">`; `PortalSidebar.tsx` NAV entry `{ to: '/portal/benefits', icon: HeartPulse, label: 'My Benefits', feature: 'benefits_admin' }` (pattern at line 16).

## Step 8 — Tests + verification

New `server/tests/benefits/` (model: `tests/employee_schedule/` — pure logic, no DB, no importlib hacks):
- `test_benefits_models.py` — Pydantic: waive/plan-id consistency, relationship literals.
- `test_enrollment_rules.py` — `resolve_active_window`, `allowed_transition` full matrix, `validate_election_payload`, `window_ends_on` math, email builders contain portal link.
- `test_eligibility_elections.py` — gap-suppression predicate incl. null-`employee_id` roster case.

Sequence:
1. `cd server && python3 -m pytest tests/benefits/ -q` + regression canaries `tests/ir_incidents -q`.
2. Migration: commit → user runs `./scripts/migrate-dev.sh`; author rehearsal `MIGRATE_REHEARSAL=1 DATABASE_URL=<dev> alembic upgrade heads`. Never prod, never auto-run.
3. `cd client && npx tsc -p tsconfig.app.json --noEmit` (bare `tsc --noEmit` checks nothing).
4. Manual smoke (dev): enable `benefits_admin` on test company → plan+tiers → open OE period → employee elects/waives/submits → client approves → `POST /benefits/run` confirms new-hire gap clears → flip scheduler row, confirm notices rows land (reserved-domain sends skipped).

## MVP cutlines (deferred)

Structured dependents table (JSONB now, no SSN); payroll deduction write-back (Finch `hris_deductions` path untouched); carrier EDI/834; SBC document uploads; evidence-of-insurability; FSA/HSA contribution elections; beneficiaries; COBRA linkage; passive re-enrollment/rollover; mid-period proration; eligibility-class targeting (all active employees eligible); broker rollups; in-app notifications.
