# Schedule Compliance Guidance — Terra Implementation Handoff

## Status and locked product decisions

This document is the implementation contract for schedule break guidance, employee-shift notes, daily notices, hour-policy warnings, minor/work-permit enforcement, and expiring credential enforcement.

Locked decisions:

- The daily location digest goes to the location operational mailbox and active managers at that location.
- An employee receives a separate private daily email only when that employee has break guidance or a visible shift note for that service date.
- V1 has one editable manager note per employee-shift. Every change is audit logged.
- During manual employee creation, the manager must answer `Meal break waiver on file? Yes / No`.
- A waiver upload is not required. The answer is an append-only manager attestation.
- A waiver attestation suppresses a break only when the approved rule for the shift permits a waiver and all rule conditions are satisfied.
- Missing or expired schedule-blocking permits/credentials prevent new scheduling.
- After the warning-only rollout, expiration automatically removes assignments for shifts starting on or after the expiration date. Removal is audited and both the employee and manager are notified.
- Legal rule content is versioned, sourced, and approved by a human reviewer. Code and AI must not invent jurisdictional requirements.

## Repository baseline and invariants

- The employee-scheduling Alembic branch currently ends at `empsched05`. The first migration in this plan must use `down_revision = "empsched05"`; later migrations chain from it. The repository intentionally has multiple Alembic heads. Do not create an unrelated merge migration.
- Scheduling tables were introduced in `server/alembic/versions/empsched01_add_employee_schedule.py`.
- All shift mutations must preserve the existing shared writer and audit conventions in `server/app/matcha/services/scheduling/shift_writes.py`.
- Existing audit action names are inputs to Fair Workweek analysis. Keep `shift.create`, `shift.update`, `shift.publish`, `assignment.create`, and `assignment.delete` unchanged.
- Existing schedule timestamps are stored and rendered as UTC wall-clock values. `client/src/types/employeeSchedule.ts:fmtTime()` deliberately reads UTC fields. This project must not silently convert existing shifts to true UTC instants or change their displayed hours.
- A location IANA timezone is introduced for local service dates, digest dispatch, and legal deadline labels. Reinterpret the stored UTC clock components in the location timezone; do not call `astimezone(location_zone)` on a stored schedule timestamp because that would change a displayed 9 AM shift into another hour.
- `schedule_rule_extractions` is a state-level scalar-threshold table. It remains the existing compliance-gate source. Do not overload it with effective-dated jurisdiction/industry break-band JSON. The new break-rule table can adapt legacy approved/curated thresholds when no structured rule set exists.
- Employee DOB remains protected in `employee_demographics`. Schedule and general employee response payloads must never return DOB.
- The worker restarts every 15 minutes and dispatches enabled entries from `_SCHEDULED_TASKS`; there is no Celery beat. Every new worker must be idempotent and its `scheduler_settings` row must be seeded disabled.
- Email copy is deterministic. Do not use Gemini or another model to compose legal guidance or notices.
- A read/evaluation failure may create a visible advisory, but it must never automatically unassign an employee.

## Canonical domain contracts

Add `server/app/matcha/services/scheduling/schedule_breaks.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo

BreakKind = Literal["meal", "rest"]
BreakPlanStatus = Literal["complete", "unmapped", "error"]


@dataclass(frozen=True)
class BreakRule:
    rule_set_id: UUID
    kind: BreakKind
    ordinal: int
    trigger_after_minutes: int
    duration_minutes: int
    paid: bool
    deadline_offset_minutes: int | None
    earliest_offset_minutes: int | None
    latest_offset_minutes: int | None
    waiver_allowed: bool
    waiver_max_shift_minutes: int | None
    citation: str


@dataclass(frozen=True)
class MealWaiverAttestation:
    id: UUID
    on_file: bool
    effective_from: date
    confirmed_by: UUID
    confirmed_at: datetime


@dataclass(frozen=True)
class BreakRequirement:
    kind: BreakKind
    ordinal: int
    duration_minutes: int
    paid: bool
    earliest_local: datetime | None
    recommended_local: datetime | None
    deadline_local: datetime | None
    waived: bool
    waiver_attestation_id: UUID | None
    citation: str
    rule_set_id: UUID


@dataclass(frozen=True)
class BreakPlan:
    status: BreakPlanStatus
    requirements: tuple[BreakRequirement, ...]
    advisories: tuple[dict, ...]
    rule_set_ids: tuple[UUID, ...]
    rule_set_hash: str


def reinterpret_schedule_wall_time(value: datetime, timezone: ZoneInfo) -> datetime:
    """Preserve stored clock fields and attach the location timezone."""
    ...


def evaluate_break_plan(
    *,
    starts_at: datetime,
    ends_at: datetime,
    timezone: ZoneInfo,
    rules: Sequence[BreakRule],
    waiver: MealWaiverAttestation | None,
) -> BreakPlan:
    ...


def render_break_requirement(requirement: BreakRequirement) -> str:
    ...


def render_break_plan(plan: BreakPlan) -> str | None:
    ...
```

Rules for the pure evaluator:

1. Shift duration follows the repository's current scheduled wall-clock convention.
2. Exact trigger boundaries are inclusive only when the approved rule says the requirement applies at that boundary. Encode this explicitly in normalized rule JSON as `trigger_operator: "gt" | "gte"` rather than assuming.
3. A deadline is emitted only when the rule supplies a deadline offset.
4. A rest break with no legal deadline can have a recommended window, but rendered copy must not say `by`.
5. An on-file waiver applies only when `waiver_allowed` is true and every waiver condition passes.
6. An inapplicable waiver creates an advisory and leaves the meal requirement intact.
7. An unmapped rule set returns `status="unmapped"`; it never returns a false clear plan.
8. Rendering examples are deterministic:
   - `Mandatory 30-minute unpaid meal break by 2 PM`
   - `One 10-minute paid rest break`
   - `Two 10-minute paid rest breaks`

Persisted `compliance_guidance` JSON uses schema version 1:

```json
{
  "schema_version": 1,
  "status": "complete",
  "evaluated_at": "2026-08-21T12:00:00Z",
  "timezone": "America/Los_Angeles",
  "rule_set_ids": ["uuid"],
  "rule_set_hash": "sha256",
  "summary": "Mandatory 30-minute unpaid meal break by 2 PM + one 10-minute paid rest break",
  "requirements": [
    {
      "kind": "meal",
      "ordinal": 1,
      "duration_minutes": 30,
      "paid": false,
      "deadline_local": "2026-08-21T14:00:00-07:00",
      "waived": false,
      "citation": "approved citation",
      "rule_set_id": "uuid"
    }
  ],
  "advisories": []
}
```

## PR 1 — Rule foundation, location readiness, waiver attestations, pure evaluation

### Migration

Create `server/alembic/versions/empsched06_schedule_guidance.py`:

```python
revision = "empsched06"
down_revision = "empsched05"
```

Add nullable `business_locations.timezone VARCHAR(64)`. Existing locations remain valid records, but cannot enable schedule digest delivery or newly publish schedules until readiness passes.

Create `schedule_break_rule_sets`:

```text
id UUID PK
jurisdiction_id UUID NULL REFERENCES jurisdictions(id) ON DELETE RESTRICT
industry_code VARCHAR(80) NULL
effective_from DATE NOT NULL
effective_to DATE NULL
rules JSONB NOT NULL
citation TEXT NOT NULL
authority_url TEXT NULL
source_type VARCHAR(20) NOT NULL CHECK csv|api|manual|legacy_curated
source_external_id VARCHAR(255) NULL
source_version VARCHAR(100) NULL
review_status VARCHAR(20) NOT NULL DEFAULT pending CHECK pending|approved|rejected
reviewed_by UUID NULL REFERENCES users(id)
reviewed_at TIMESTAMPTZ NULL
is_active BOOLEAN NOT NULL DEFAULT true
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Constraints and indexes:

- `effective_to IS NULL OR effective_to >= effective_from`.
- Approved rows require non-null `jurisdiction_id`, `reviewed_by`, and `reviewed_at`.
- Partial lookup index on `(jurisdiction_id, industry_code, effective_from DESC)` for approved active rows.
- Unique partial external-source index on `(source_type, source_external_id, source_version)` when `source_external_id IS NOT NULL`.
- `rules` must be a JSON object. Full shape validation remains in Pydantic/service code.
- Never update approved legal content in place. Deactivate it and insert a new version.

Create append-only `employee_compliance_attestations`:

```text
id UUID PK
company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE
employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE
attestation_type VARCHAR(60) NOT NULL CHECK meal_break_waiver_on_file
value BOOLEAN NOT NULL
effective_from DATE NOT NULL
confirmed_by UUID NOT NULL REFERENCES users(id)
confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now()
note TEXT NULL
```

Index `(company_id, employee_id, attestation_type, effective_from DESC, confirmed_at DESC)`. There is no update or delete endpoint. A later `false` row supersedes an earlier `true` row.

Add to `schedule_shift_assignments`:

```text
manager_note TEXT NULL
manager_note_visible_to_employee BOOLEAN NOT NULL DEFAULT true
manager_note_include_in_location_digest BOOLEAN NOT NULL DEFAULT true
manager_note_send_employee_notice BOOLEAN NOT NULL DEFAULT true
manager_note_updated_by UUID NULL REFERENCES users(id)
manager_note_updated_at TIMESTAMPTZ NULL
compliance_guidance JSONB NULL
guidance_evaluated_at TIMESTAMPTZ NULL
guidance_ruleset_hash VARCHAR(64) NULL
```

### Rule import and review

Add:

- `server/app/core/models/schedule_break_rules.py`
- `server/app/core/services/schedule_break_rule_import.py`
- `server/app/core/routes/admin/schedule_break_rules.py`
- `server/scripts/import_schedule_break_rules.py`

Contracts:

```python
class BreakRuleSetImport(BaseModel):
    jurisdiction_id: UUID | None = None
    industry_code: str | None = None
    effective_from: date
    effective_to: date | None = None
    rules: BreakRuleSetPayload
    citation: str
    authority_url: str | None = None
    source_type: Literal["csv", "api", "manual"]
    source_external_id: str | None = None
    source_version: str | None = None


class BreakRuleSetReview(BaseModel):
    decision: Literal["approved", "rejected"]


async def import_break_rule_sets(
    conn,
    *,
    rows: Sequence[BreakRuleSetImport],
    actor_user_id: UUID,
) -> BreakRuleImportResult:
    ...


async def review_break_rule_set(
    conn,
    *,
    rule_set_id: UUID,
    decision: Literal["approved", "rejected"],
    actor_user_id: UUID,
) -> dict:
    ...
```

Routes are platform-admin only:

```text
POST /admin/schedule-break-rules/import
GET  /admin/schedule-break-rules?review_status=pending
POST /admin/schedule-break-rules/{rule_set_id}/review
```

CSV columns:

```text
jurisdiction_id,industry_code,effective_from,effective_to,citation,authority_url,source_external_id,source_version,rules_json
```

CSV and API must call the same validator/service. Imports always begin as `pending`.

### Rule resolution and location readiness

Add `server/app/matcha/services/scheduling/schedule_break_rule_store.py`:

```python
async def resolve_break_rules(
    conn,
    *,
    company_id: UUID,
    location_id: UUID,
    shift_date: date,
) -> ResolvedBreakRules:
    ...


async def get_current_meal_waiver_attestation(
    conn,
    *,
    company_id: UUID,
    employee_id: UUID,
    shift_date: date,
) -> MealWaiverAttestation | None:
    ...
```

Resolution order:

1. Resolve the location's exact `jurisdiction_id` and ancestor chain.
2. Resolve industry from location NAICS/canonical industry, then company canonical industry fallback.
3. Select approved active rules effective on the shift date.
4. Prefer the most specific jurisdiction, then industry-specific over general at the same jurisdiction.
5. If no structured break set exists, adapt supported legacy curated/approved values from `schedule_compliance.py` and `schedule_rule_extractions` without changing the existing violation engine.
6. If still unmapped, return unmapped guidance and a visible advisory.

Add `server/app/matcha/services/scheduling/schedule_location_readiness.py`:

```python
@dataclass(frozen=True)
class LocationReadiness:
    ready_to_publish: bool
    missing_fields: tuple[str, ...]
    jurisdiction_id: UUID | None
    timezone: str | None
    industry_code: str | None


async def get_schedule_location_readiness(
    conn,
    company_id: UUID,
    location_id: UUID | None,
) -> LocationReadiness:
    ...


async def assert_schedule_location_ready_to_publish(
    conn,
    company_id: UUID,
    location_id: UUID | None,
) -> None:
    ...
```

Expose the readiness result through:

```text
GET /employee-schedule/locations/{location_id}/readiness
```

The weekly schedule response may embed the selected location's readiness so the manager UI can render one banner without a second request. The standalone endpoint remains the source for settings and publication flows.

Readiness requires address, city, state/region, postal code, jurisdiction ID, timezone, and a resolvable industry. Drafts remain allowed. New publication is blocked with structured `422` detail:

```json
{
  "code": "schedule_location_not_ready",
  "location_id": "uuid-or-null",
  "missing_fields": ["address", "timezone"]
}
```

Call the readiness assertion from all publication paths in `server/app/matcha/routes/employee_schedule/shifts.py`, plus chat/template paths that create published shifts. Existing published shifts are grandfathered; do not unpublish them.

Update location files:

- `server/app/orm/location.py`
- `server/app/core/models/compliance.py`
- `server/app/core/services/compliance_service/_locations.py`
- `client/src/types/compliance.ts`
- `client/src/components/compliance/ComplianceLocationModal.tsx`

### PR 1 tests

Add:

- `server/tests/employee_schedule/test_break_plans.py`
- `server/tests/employee_schedule/test_break_rule_store.py`
- `server/tests/employee_schedule/test_schedule_location_readiness.py`
- `server/tests/alembic/test_schedule_guidance_migration.py`

Required cases:

1. A 9 AM start with a five-hour deadline renders `by 2 PM` without changing the stored/displayed 9 AM start.
2. Trigger `gt` and `gte` differ at the exact boundary.
3. First and second meals.
4. Zero, one, and multiple paid rest breaks.
5. Paid/unpaid rendering and singular/plural rendering.
6. Overnight shift.
7. DST transition preserves the repository's wall-clock schedule convention.
8. City/industry rule beats state/general rule.
9. Effective-date and expiration boundaries.
10. Current `true`, current `false`, missing, superseded, and future-dated waiver attestations.
11. Waiver on file but not permitted leaves the meal active and emits an advisory.
12. Unmapped jurisdiction is not reported as compliant.
13. Pending/rejected/inactive rule sets never enforce.
14. Draft location can be incomplete; every publish path refuses an incomplete location.
15. Migration upgrade/downgrade, checks, indexes, and `empsched05` ancestry.

PR 1 is complete when pure tests pass, rule imports cannot self-approve, drafts still work, and no existing schedule time changes presentation.

## PR 2 — Assignment guidance, manager notes, employee-add waiver question, UI

### Guidance orchestration

Add `server/app/matcha/services/scheduling/schedule_guidance.py`:

```python
async def build_assignment_guidance(
    conn,
    company_id: UUID,
    *,
    shift_row,
    employee_id: UUID,
) -> dict:
    ...


async def reconcile_assignment_guidance(
    conn,
    company_id: UUID,
    *,
    shift_ids: Sequence[UUID] | None = None,
    employee_ids: Sequence[UUID] | None = None,
) -> int:
    ...
```

Reconcile after:

- `create_shift_core`: all inserted assignments.
- `apply_assignment_core`: the inserted assignment.
- `retime_shift_core`: every assignment on the shift.
- Shift break/location changes in `shifts.py`.
- Meal-waiver attestation changes: future non-cancelled assignments for that employee.
- Approved break-rule changes: affected future assignments, through a bounded repair worker or explicit administrative reconcile action.

The guidance write occurs in the caller's transaction. An evaluation exception stores `status="error"` with a generic advisory; it does not abort a previously valid schedule mutation unless the existing compliance gate independently returns a hard block.

### Preserve refused chat edits

`execute_edit_proposal()` stages assignment deletion and may restore it. Expand `restore_assignment_raw()` in `shift_writes.py`:

```python
async def restore_assignment_raw(
    conn,
    company_id: UUID,
    *,
    assignment_row: Mapping[str, Any],
) -> None:
    ...
```

Restore every assignment-owned field: ID if safe, company, shift, employee, status, assigned-by/at, manager-note fields, compliance guidance, evaluation timestamp, and rule hash. Update `schedule_chat.py` to pass its saved `SELECT *` row. A refused reassign must be a true no-op, including note and guidance preservation.

### Models and routes

Add to `server/app/matcha/models/scheduling/employee_schedule.py`:

```python
class AssignmentNoteUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    visible_to_employee: bool = True
    include_in_location_digest: bool = True
    send_employee_notice: bool = True


class MealWaiverAttestationUpdate(BaseModel):
    on_file: bool
    effective_from: date = Field(default_factory=date.today)
    note: str | None = Field(default=None, max_length=500)
```

Add to `server/app/matcha/routes/employee_schedule/assignments.py`:

```text
PUT /employee-schedule/shifts/{shift_id}/assignments/{employee_id}/note
```

Semantics:

- Tenant-scope the shift and employee and require the assignment to exist.
- Update the one current note and visibility flags.
- Write `assignment.note_update` to `schedule_audit_log` with before/after values and no unrelated shift mutation.
- Clearing the note sets it to null and is audited.

Add `server/app/matcha/routes/employees/compliance_attestations.py`:

```text
GET /employees/{employee_id}/compliance-attestations
PUT /employees/{employee_id}/compliance-attestations/meal-break-waiver
```

The PUT inserts an append-only attestation, then reconciles that employee's future assignments. Audit identity comes from `confirmed_by`/`confirmed_at` in the attestation table.

Extend `EmployeeCreateRequest` in `server/app/matcha/routes/employees/crud.py`:

```python
meal_break_waiver_on_file: bool | None = None
```

Use tri-state semantics:

- `true`: manager confirmed yes.
- `false`: manager confirmed no.
- omitted/null: unknown; do not fabricate a `false` attestation.

The manual UI must require Yes or No. API/HRIS/bulk integrations may initially omit it, which produces unknown status and does not waive a break. Insert the employee and attestation in one transaction.

The standard employee response may return:

```json
{"meal_break_waiver_status": "yes|no|unknown"}
```

It must not return the confirmer or audit history unless the dedicated admin endpoint is called.

### Serialization privacy

Modify `fetch_shifts()` and `fetch_shift_by_id()` in `server/app/matcha/routes/employee_schedule/_shared.py` to select assignment note/guidance fields.

Add a viewer parameter:

```python
async def fetch_shifts(
    ...,
    viewer_employee_id: UUID | None = None,
) -> list[dict]:
    ...
```

- Admin calls omit `viewer_employee_id` and receive all assignment guidance and note controls.
- Portal calls pass the signed-in employee ID.
- On the portal, private note/guidance fields are attached only to the assignment whose `employee_id == viewer_employee_id`.
- Existing coworker assignment fields remain unchanged; never attach another employee's note or compliance details.
- If `manager_note_visible_to_employee=false`, omit the note from the portal and employee email even for the subject employee.

Assignment response example:

```json
{
  "employee_id": "uuid",
  "name": "Jessa",
  "status": "assigned",
  "manager_note": "Harassment training due today",
  "manager_note_visible_to_employee": true,
  "manager_note_include_in_location_digest": true,
  "manager_note_send_employee_notice": true,
  "compliance_guidance": {
    "schema_version": 1,
    "status": "complete",
    "summary": "Mandatory 30-minute unpaid meal break by 2 PM + one 10-minute paid rest break",
    "requirements": []
  }
}
```

### Frontend

Modify:

- `client/src/types/employeeSchedule.ts`
- `client/src/api/employees/employeeSchedule.ts`
- `client/src/pages/app/employees/EmployeeSchedule.tsx`
- `client/src/pages/portal/PortalSchedule.tsx`
- `client/src/components/employees/MultiBatchModal.tsx`
- `client/src/pages/app/employees/EmployeeDetail.tsx`
- `client/src/types/employee.ts`

Prefer extracting:

- `client/src/components/employees/schedule/AssignmentGuidance.tsx`
- `client/src/components/employees/schedule/AssignmentNoteEditor.tsx`
- `client/src/components/employees/MealWaiverAttestationControl.tsx`

Manager schedule behavior:

- Each assignee row shows a break badge when guidance has requirements.
- Expanding the assignee shows structured requirements, citation, waiver state, and the note editor.
- Unmapped/error guidance is visually distinct and never displays `No break required`.
- The employee-add modal requires an explicit Yes/No waiver selection for each row.
- Employee detail permits a new audited Yes/No attestation.

Portal behavior:

- The shift card shows only that employee's break summary and visible note.
- Hidden notes and other employees' guidance never render or appear in DOM props.

### PR 2 tests

Add:

- `server/tests/employee_schedule/test_assignment_guidance.py`
- `server/tests/employee_schedule/test_assignment_notes.py`
- `server/tests/employee_schedule/test_meal_waiver_attestations.py`
- `client/src/components/employees/schedule/AssignmentGuidance.test.tsx`
- `client/src/components/employees/schedule/AssignmentNoteEditor.test.tsx`
- `client/src/pages/portal/PortalSchedule.test.tsx`

Required cases:

1. Create, assign, retime, break update, location update, and waiver update reconcile guidance.
2. Assignment note create/update/clear is tenant-scoped and audited.
3. One note per assignment; updating does not add multiple current notes.
4. Admin sees all notes; employee sees only their own visible note/guidance.
5. Hidden note is absent from portal payload and UI.
6. Refused chat reassign restores every assignment field byte-for-byte and emits no delete/create audit pair.
7. Manual employee add refuses submission until Yes or No is chosen.
8. API omission creates unknown, not a false attestation.
9. A waiver change recomputes future shifts but does not rewrite past/cancelled assignments.

## PR 3 — Location digest and private employee daily notices

### Migration

Create `server/alembic/versions/empsched07_schedule_digest.py`:

```python
revision = "empsched07"
down_revision = "empsched06"
```

Create `schedule_digest_settings`:

```text
id UUID PK
company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE
location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE
enabled BOOLEAN NOT NULL DEFAULT false
location_recipient_email VARCHAR(320) NULL
send_local_time TIME NOT NULL DEFAULT '05:00'
send_window_minutes INTEGER NOT NULL DEFAULT 30
send_employee_notices BOOLEAN NOT NULL DEFAULT true
include_breaks BOOLEAN NOT NULL DEFAULT true
include_manager_notes BOOLEAN NOT NULL DEFAULT true
created_by UUID NULL REFERENCES users(id)
updated_by UUID NULL REFERENCES users(id)
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE(company_id, location_id)
```

Create `schedule_digest_deliveries`:

```text
id UUID PK
company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE
location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE
service_date DATE NOT NULL
delivery_kind VARCHAR(30) NOT NULL CHECK location_digest|employee_notice
recipient_type VARCHAR(20) NOT NULL CHECK location|manager|employee
recipient_key VARCHAR(255) NOT NULL
recipient_email VARCHAR(320) NOT NULL
employee_id UUID NULL REFERENCES employees(id) ON DELETE SET NULL
payload_hash VARCHAR(64) NOT NULL
status VARCHAR(20) NOT NULL CHECK pending|sent|failed|skipped
attempts INTEGER NOT NULL DEFAULT 0
last_error TEXT NULL
sent_at TIMESTAMPTZ NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE(company_id, service_date, delivery_kind, recipient_key)
```

`recipient_key` is stable and avoids nullable unique-key behavior:

- `location:<normalized-email>`
- `manager:<employee-uuid>`
- `employee:<employee-uuid>`

Seed disabled scheduler row `schedule_daily_digest` with a bounded `max_per_cycle`. Downgrade deletes only that task key and these tables.

### Services

Add `server/app/matcha/services/scheduling/schedule_digest.py`:

```python
@dataclass(frozen=True)
class DigestRecipient:
    recipient_type: Literal["location", "manager", "employee"]
    recipient_key: str
    email: str
    name: str | None
    employee_id: UUID | None


async def resolve_location_digest_recipients(
    conn,
    company_id: UUID,
    location_id: UUID,
) -> tuple[DigestRecipient, ...]:
    ...


async def build_location_daily_digest(
    conn,
    company_id: UUID,
    location_id: UUID,
    service_date: date,
) -> ScheduleDailyDigest:
    ...


async def build_employee_daily_notice(
    conn,
    company_id: UUID,
    employee_id: UUID,
    service_date: date,
) -> EmployeeDailyNotice | None:
    ...


def render_location_digest_text(digest: ScheduleDailyDigest) -> str:
    ...


def render_location_digest_html(digest: ScheduleDailyDigest) -> str:
    ...


def render_employee_notice_text(notice: EmployeeDailyNotice) -> str:
    ...


def render_employee_notice_html(notice: EmployeeDailyNotice) -> str:
    ...
```

Location recipients:

1. The configured operational mailbox, if present.
2. Active employees at the location where `is_manager=true` or `is_supervisor=true`.
3. Active employees at the location who are referenced as `manager_id` by another active employee at that location.
4. Deduplicate normalized email addresses.
5. Use work email first and personal email only when work email is absent.

Digest source shifts:

- Published shifts whose start belongs to the location's local service date under the existing wall-clock convention.
- Exclude cancelled shifts and declined assignments.
- Sort by scheduled start, then employee name.
- Include break summaries for all active assignments.
- Include only notes marked `include_in_location_digest=true`.
- The location/manager digest may list the whole location roster for that day.

Employee notices:

- One private email per employee per service date, combining all of their applicable shifts.
- Send only when at least one break requirement or visible note exists.
- Always include applicable break guidance.
- Include a manager note only when both `visible_to_employee=true` and `send_employee_notice=true`.
- Never include another employee's name, note, waiver state, credential state, or break plan.

Example location text:

```text
Good Morning Team Wilshire!

Today's Breaks are as Follows:

Jessa - Mandatory 30-minute unpaid meal break by 2 PM + one 10-minute paid rest break
Gerald - Mandatory 30-minute unpaid meal break by 4 PM + two 10-minute paid rest breaks

Additional shift notes from leadership:

Marissa - Must complete harassment training by end of day

Have a great shift!
```

Example employee text:

```text
Good morning Jessa,

For your shift today:
- Mandatory 30-minute unpaid meal break by 2 PM
- One 10-minute paid rest break
- Harassment training is due today

Have a great shift!
```

### Email and worker

Add `server/app/core/services/email/scheduling.py` with `SchedulingEmailMixin`:

```python
async def send_schedule_location_digest(...)-> bool:
    return await self._send_with_fallback(...)


async def send_schedule_employee_notice(...)-> bool:
    return await self._send_with_fallback(...)
```

Register it in `server/app/core/services/email/client.py`.

Add `server/app/workers/tasks/schedule_daily_digest.py`:

```python
async def _run_schedule_daily_digest(now_utc: datetime) -> dict:
    ...


@celery_app.task(bind=True, max_retries=1, name="schedule.daily_digest")
def run_schedule_daily_digest(self) -> dict:
    ...
```

Add the task tuple to `_SCHEDULED_TASKS` in `server/app/workers/celery_app.py`. The worker must fail closed when the scheduler row is missing/disabled, claim delivery rows before sending, retry failed rows without creating duplicates, and never resend a successful scheduled delivery.

### Routes and frontend settings

Add `server/app/matcha/routes/employee_schedule/digests.py` and include it from the package router:

```text
GET  /employee-schedule/digest-settings/{location_id}
PUT  /employee-schedule/digest-settings/{location_id}
POST /employee-schedule/digests/{location_id}/preview?service_date=YYYY-MM-DD
POST /employee-schedule/digests/{location_id}/send?service_date=YYYY-MM-DD
```

Enabling settings requires location readiness plus at least one resolved location/manager recipient. Preview sends nothing and writes no delivery row. Manual send uses an explicit request idempotency key and is audited.

Add API/types and a settings/preview panel to the schedule page. The preview must show separate location and employee-message sections so privacy is inspectable before enabling.

### PR 3 tests

Add:

- `server/tests/employee_schedule/test_schedule_digest.py`
- `server/tests/workers/test_schedule_daily_digest.py`
- `server/tests/email/test_schedule_email.py`
- `client/src/components/employees/schedule/ScheduleDigestSettings.test.tsx`

Required cases:

1. Location mailbox plus all three manager-resolution paths; duplicate emails collapse.
2. Only published/non-declined assignments appear.
3. Local service date and dispatch window, including DST dates.
4. Exact deterministic text and HTML escaping.
5. Manager digest includes only opted-in notes.
6. Employee email contains only that employee's data.
7. Employee with no break/note receives no email and no pending delivery.
8. Successful delivery is not resent on the next 15-minute restart.
9. Failed delivery retries the same row.
10. Missing/disabled scheduler and incomplete location fail closed.
11. Preview has no side effect.

## PR 4 — FT/PT hour warnings, DOB/minor permits, credential eligibility

### Migration

Create `server/alembic/versions/empsched08_schedule_eligibility.py`:

```python
revision = "empsched08"
down_revision = "empsched07"
```

Create `schedule_hour_limits`:

```text
id UUID PK
company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE
employment_type VARCHAR(30) NOT NULL
warning_hours NUMERIC(6,2) NOT NULL
hard_cap_hours NUMERIC(6,2) NULL
created_by UUID NULL REFERENCES users(id)
updated_by UUID NULL REFERENCES users(id)
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE(company_id, employment_type)
CHECK warning_hours >= 0
CHECK hard_cap_hours IS NULL OR hard_cap_hours >= warning_hours
```

Create `schedule_eligibility_settings`:

```text
company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE
reminder_days INTEGER NOT NULL DEFAULT 14
enforcement_mode VARCHAR(20) NOT NULL DEFAULT warn_only CHECK warn_only|block|block_and_unassign
updated_by UUID NULL REFERENCES users(id)
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Extend `credential_requirement_templates`:

```text
industry_code VARCHAR(80) NULL
renewal_notice_days INTEGER NOT NULL DEFAULT 14
scheduling_effect VARCHAR(20) NOT NULL DEFAULT none CHECK none|advisory|block
```

Extend `employee_credential_requirements`:

```text
expires_on DATE NULL
scheduling_effect VARCHAR(20) NOT NULL DEFAULT none CHECK none|advisory|block
schedule_constraints JSONB NULL
```

Create `schedule_eligibility_notifications`:

```text
id UUID PK
company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE
employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE
requirement_id UUID NOT NULL REFERENCES employee_credential_requirements(id) ON DELETE CASCADE
expires_on DATE NOT NULL
notification_kind VARCHAR(30) NOT NULL CHECK expiry_warning|expired|unassigned
recipient_type VARCHAR(20) NOT NULL CHECK employee|manager
recipient_key VARCHAR(255) NOT NULL
recipient_email VARCHAR(320) NOT NULL
status VARCHAR(20) NOT NULL CHECK pending|sent|failed|skipped
attempts INTEGER NOT NULL DEFAULT 0
sent_at TIMESTAMPTZ NULL
last_error TEXT NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE(requirement_id, expires_on, notification_kind, recipient_key)
```

Seed disabled `schedule_eligibility_sweep` scheduler row.

### Hour-policy service

Add `server/app/matcha/services/scheduling/schedule_hours.py`:

```python
@dataclass(frozen=True)
class HourLimit:
    employment_type: str
    warning_hours: Decimal
    hard_cap_hours: Decimal | None


async def resolve_weekly_hour_limit(
    conn,
    company_id: UUID,
    employee_id: UUID,
) -> HourLimit | None:
    ...


def check_weekly_policy_hours(
    *,
    projected_hours: Decimal,
    limit: HourLimit,
) -> list[dict]:
    ...
```

- `warning_hours` returns a forceable `409` issue with code `employment_type_hours`.
- A forced write records employee, projected hours, configured limit, manager, and source path in the existing schedule audit.
- `hard_cap_hours`, when configured, returns a non-forceable block.
- These are company policies and must not be labeled statutory overtime.
- Existing overtime checks remain separate.

### DOB and minor status

Extend manual employee creation with optional write-only `date_of_birth: date | None`. Store it in `employee_demographics` in the same transaction; never in `employees`.

Add a protected route for replacement/correction:

```text
PUT /employees/{employee_id}/demographics/date-of-birth
```

Return only:

```json
{"minor_status": "minor|adult|unknown", "updated": true}
```

Do not return DOB through list, detail, schedule, portal, digest, or audit payloads. Audit only that DOB was added/changed, not its value.

Age is calculated as of each shift's local service date. Unknown DOB creates a visible age-verification advisory where minor rules could apply; it does not classify everyone as a minor.

### Credential and permit service

Add `server/app/matcha/services/scheduling/schedule_eligibility.py`:

```python
@dataclass(frozen=True)
class EligibilityIssue:
    code: Literal[
        "age_unverified",
        "minor_permit_missing",
        "minor_permit_expired",
        "permit_hours_exceeded",
        "credential_missing",
        "credential_expired",
    ]
    severity: Literal["advisory", "block"]
    message: str
    requirement_id: UUID | None
    expires_on: date | None
    citation: str | None


async def evaluate_schedule_eligibility(
    conn,
    company_id: UUID,
    *,
    employee_id: UUID,
    shift_row,
) -> list[EligibilityIssue]:
    ...
```

Rules:

- Work permit and food-handler card are credential types, not special-purpose columns.
- Expand portal/admin accepted document types to include `minor_work_permit` and `food_handler_card`.
- Extracted expiration dates remain pending until manager verification. AI extraction alone never clears a block.
- Manager verification copies the reviewed expiration to `employee_credential_requirements.expires_on` and materializes validated schedule constraints.
- `schedule_constraints` supports a versioned validated shape such as daily/weekly maximum minutes and earliest/latest permitted local work time. Reject unknown keys.
- A required `block` credential that is missing or expired is a non-forceable block.
- An unrelated or optional credential does not block.
- Broaden `credential_template_service.py` beyond clinical roles using approved industry and job/role mappings. Do not infer a food-handler requirement from free text at scheduling time.

Integrate hour and eligibility issues into `check_shift_compliance()` so every existing REST, chat, swap, move, duplicate, and template path receives the same issue shape. `raise_for_violations()` retains the existing forceable-advisory/non-forceable-block behavior.

Add `server/app/matcha/routes/employee_schedule/policy_settings.py` and include it from the package router:

```text
GET /employee-schedule/policy-settings
PUT /employee-schedule/policy-settings/hour-limits/{employment_type}
PUT /employee-schedule/policy-settings/eligibility
```

Request examples:

```json
{
  "warning_hours": 29.5,
  "hard_cap_hours": null
}
```

```json
{
  "reminder_days": 14,
  "enforcement_mode": "warn_only"
}
```

Only schedule-managing admins/clients can change these settings. Each update writes a schedule audit entry containing before/after values. Add a schedule settings panel for FT/PT thresholds and eligibility mode; display plain language that hour thresholds are company policies, not statutory overtime rules.

### PR 4 tests

Add:

- `server/tests/employee_schedule/test_schedule_hour_limits.py`
- `server/tests/employee_schedule/test_schedule_eligibility.py`
- `server/tests/employee_schedule/test_schedule_eligibility_routes.py`
- `server/tests/employees/test_employee_demographics_schedule.py`
- `server/tests/alembic/test_schedule_eligibility_migration.py`

Required cases:

1. FT/PT threshold, exact boundary, force override, audit, and optional hard cap.
2. Policy warning remains distinct from statutory overtime.
3. Age is correct immediately before/on the eighteenth birthday.
4. DOB never appears in standard API, portal, digest, or audit payloads.
5. Minor permit missing, expired, renewed, and constraint violations.
6. Expired required food-handler card blocks; unrelated credential does not.
7. Extracted-but-unverified expiration does not clear a block.
8. Every scheduling entry path enforces the same hard block and no `force=true` bypass works.
9. A compliance-service read failure returns advisory and never removes an assignment.

## PR 5 — Eligibility reminders and automatic future unassignment

Add `server/app/workers/tasks/schedule_eligibility_sweep.py`:

```python
async def _run_schedule_eligibility_sweep(
    now_utc: datetime,
) -> dict:
    ...


@celery_app.task(bind=True, max_retries=1, name="schedule.eligibility_sweep")
def run_schedule_eligibility_sweep(self) -> dict:
    ...
```

Behavior:

1. Fail closed when the scheduler row is absent/disabled.
2. For each company, read `reminder_days` and `enforcement_mode`.
3. At the warning boundary, create idempotent employee and manager deliveries.
4. Resolve employee work email then personal email. Resolve direct manager email; if unavailable, use active location managers. Deduplicate.
5. A renewal with a new expiration date gets a new notification identity; the old expiration is not resent.
6. In `warn_only`, notify and surface issues but do not block or remove.
7. In `block`, prevent new assignments but do not remove existing ones.
8. In `block_and_unassign`, remove only assignments for non-cancelled shifts whose start date is on/after expiration.
9. Use `remove_assignment_core()` with `actor_user_id=None` and audit details:

```json
{
  "source": "schedule_eligibility_sweep",
  "requirement_id": "uuid",
  "reason": "credential_expired",
  "expires_on": "2026-09-01"
}
```

10. Update the writer type annotation to accept a nullable system actor; the audit table already permits null.
11. Notify the employee and manager after committed removal.
12. If eligibility evaluation or a required query fails, roll back that employee's removal batch and continue other employees. Never remove on unknown state.

Add deterministic email methods for expiry warning, expiration, and unassignment to `SchedulingEmailMixin`.

Tests:

- `server/tests/workers/test_schedule_eligibility_sweep.py`
- `server/tests/email/test_schedule_eligibility_email.py`

Required cases:

1. D-14 warning goes once to employee and manager.
2. No duplicate on the next worker restart.
3. Renewed expiration suppresses old expiration action.
4. Warn-only and block modes never unassign.
5. Block-and-unassign removes future/on-date shifts only, not past shifts.
6. Every removal has one existing `assignment.delete` audit row plus source details.
7. A failed transaction sends no false removal email.
8. One employee failure does not strand the company sweep.

## API error and warning shapes

Keep all scheduling issues in the existing list-of-dicts convention. New codes:

```text
schedule_location_not_ready
break_rules_unmapped
meal_waiver_inapplicable
employment_type_hours
age_unverified
minor_permit_missing
minor_permit_expired
permit_hours_exceeded
credential_missing
credential_expired
```

Each issue must include:

```json
{
  "check": "stable_check_name",
  "code": "stable_machine_code",
  "severity": "advisory|block",
  "message": "deterministic human text",
  "statute": "citation-or-null",
  "state": "CA-or-null",
  "metadata": {}
}
```

Advisories remain forceable through the existing `409` + `force=true` flow. Blocks remain `422` and non-forceable.

## Cross-cutting acceptance criteria

The feature is not complete until all of these hold:

1. No scheduling write path can bypass a hard credential/permit block.
2. No employee can see another employee's note, break plan, waiver state, age state, or credential state.
3. A daily retry cannot duplicate a successfully sent message.
4. Legal copy comes from structured approved rules and deterministic rendering.
5. Pending/imported legal content cannot enforce before review.
6. Existing schedule wall-clock display remains unchanged.
7. Existing Fair Workweek audit action names and snapshots remain intact.
8. Refused chat edits preserve assignment notes and cached guidance.
9. Missing rule/DOB/credential data is visible as unknown, never silently clear.
10. Automated expiration processing cannot unassign after a read/evaluation failure.
11. Every automatic removal is recoverable from the audit trail and names the requirement/expiration that caused it.
12. All scheduler rows are disabled by default and every worker is bounded by `max_per_cycle`.

## Verification commands

Run focused tests after each PR, then the full affected suites:

```bash
cd server
./venv/bin/python -m pytest tests/employee_schedule tests/workers tests/email tests/alembic -q
alembic heads
```

```bash
cd client
npm run test:run -- employeeSchedule PortalSchedule AssignmentGuidance AssignmentNoteEditor ScheduleDigestSettings
npm run build
```

Also run the existing schedule-chat, assignment-move, shift-write, shift-update, training-gate, and warning-event suites because the new hooks touch their shared paths.

## Rollout order

1. Deploy migrations and UI with digest workers disabled and eligibility mode `warn_only`.
2. Load and review structured break rules; verify unmapped/readiness dashboards.
3. Backfill assignment guidance in bounded batches.
4. Enable manager note and schedule display.
5. Enable digest for internal/test locations, previewing both location and employee payloads.
6. Enable daily digest by selected location.
7. Backfill credential expirations and verify manager-reviewed constraints.
8. Move selected companies from `warn_only` to `block`.
9. After at least one complete reminder window and data-quality review, move selected companies to `block_and_unassign`.

## Terra handoff instruction

Implement one PR section at a time. Begin with PR 1 only. Before editing, read the applicable repository instruction files and re-check `git status` plus `alembic heads`. Preserve unrelated user changes. Use `apply_patch` for edits. Do not source legal rules from model memory; use synthetic fixtures in tests until approved source rows are provided. Run the focused tests for the current PR and report any pre-existing failures separately. Do not begin the next PR until the current PR's acceptance criteria pass.
