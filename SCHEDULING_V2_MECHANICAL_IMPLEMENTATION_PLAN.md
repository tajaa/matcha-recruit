# Scheduling v2 — mechanical implementation plan

## 1. Objective

Complete Matcha scheduling around the foundation already on `main`:

1. Employee profiles own job qualifications, explicit availability state, and weekly-hour targets.
2. Minor work permits carry structured, enforceable time/hour restrictions.
3. A manager can build a draft week from a template or from scratch and run one deterministic whole-week review.
4. Auto-assignment produces a reviewable proposal from hard eligibility constraints and documented fairness objectives.
5. Breaks are planned per assignment and checked against job-level floor coverage.
6. Huume reads the deterministic outputs, explains them, and stages changes through the existing confirmation harness.

This document assumes `main` at or after `fe3822d` (2026-08-27). At that point the full editor already mounts Jobs & Credentials, week templates already generate draft shifts, assignments already enforce conflicts/availability/job qualification/compliance, and Huume schedule writes already use staged confirmation.

## 2. Non-negotiable invariants

- Keep `schedule_shifts.status` as the durable draft/published boundary. Do not add a second schedule-version system.
- Auto-assignment and break planning create proposals only. They never mutate live assignments during generation.
- Applying a proposal requires a later explicit manager action and a current snapshot match.
- All assignment writes continue through `apply_assignment_core()` / `remove_assignment_core()` in `server/app/matcha/services/scheduling/shift_writes.py`.
- Preserve audit action names `assignment.create`, `assignment.delete`, and `shift.update`; Fair Workweek analytics depend on them.
- Re-run tenant, location, employee, qualification, credential, permit, conflict, availability, and compliance checks at apply time.
- A hard compliance block is never bypassed by `force=true`.
- LLM output never decides whether a schedule is lawful, whether an employee is eligible, or how the solver scores a candidate.
- Protected traits are not solver inputs. DOB/age is used only for child-labor protection.
- Existing manual scheduling remains backward compatible while scheduling-profile data is collected.
- New DB-facing tests use fake asyncpg connections unless the test is explicitly a migration/schema test. Do not point scheduling tests at a live mutable DB.
- Keep the current UTC-wall-clock convention. When a rule needs local clock fields, reinterpret the stored clock in the location timezone; do not convert `16:00Z` into `09:00` Pacific.

## 3. Deliberate v1 scope cuts

- No sales/traffic forecasting. Floor flow uses manager-authored coverage requirements.
- No time-clock proof that a break was actually taken. This feature plans scheduled breaks only.
- No automatic replacement of existing assignments. The first auto-assign release fills open slots; `rebalance_existing=false` is mandatory.
- No template operation deletes or replaces published shifts.
- No automatic Huume application of an assignment or break plan.
- No claim that an unmapped jurisdiction is compliant. Preserve `unmapped`/`verify manually` behavior.
- No performance rating, tenure, attendance, disciplinary record, or manager sentiment in fairness scoring.

## 4. Delivery sequence

| PR | Outcome | Migration |
| --- | --- | --- |
| A | Employee job/profile inputs and explicit availability | `empsched16` → `empsched15` |
| B | Structured minor-permit restrictions | `empsched17` → `empsched16` |
| C | Template preview/apply inside editor + whole-week review | no new table |
| D | Proposal-only auto-assignment | `empsched18` → `empsched17` |
| E | Assignment-level breaks and floor coverage | `empsched19` → `empsched18` |
| F | Huume review/assignment/break tools | no migration |

Each PR is independently deployable. PRs A–C must ship before enabling PR D. PR E may follow D but its hard inputs must eventually participate in D's candidate/solution validation.

---

# PR A — employee scheduling inputs

## A1. Migration

Create `server/alembic/versions/empsched16_employee_scheduling_profiles.py`:

```python
revision = "empsched16"
down_revision = "empsched15"
```

Alter `schedule_job_employees`:

```sql
ALTER TABLE schedule_job_employees
  ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN qualification_status VARCHAR(20) NOT NULL DEFAULT 'active',
  ADD COLUMN qualified_from DATE,
  ADD COLUMN qualified_until DATE,
  ADD COLUMN notes TEXT;

ALTER TABLE schedule_job_employees
  ADD CONSTRAINT schedule_job_employees_status_check
  CHECK (qualification_status IN ('active', 'training', 'suspended'));

ALTER TABLE schedule_job_employees
  ADD CONSTRAINT schedule_job_employees_dates_check
  CHECK (qualified_until IS NULL OR qualified_from IS NULL OR qualified_until >= qualified_from);

CREATE UNIQUE INDEX uniq_schedule_job_employee_primary
  ON schedule_job_employees(company_id, employee_id)
  WHERE is_primary AND qualification_status = 'active';
```

Create the one-row-per-employee scheduling profile:

```sql
CREATE TABLE employee_schedule_profiles (
  employee_id UUID PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  availability_state VARCHAR(24) NOT NULL DEFAULT 'unconfirmed'
    CHECK (availability_state IN ('unconfirmed', 'always_available', 'windows')),
  availability_confirmed_at TIMESTAMPTZ,
  availability_confirmed_by UUID REFERENCES users(id) ON DELETE SET NULL,
  min_weekly_minutes INTEGER CHECK (min_weekly_minutes BETWEEN 0 AND 10080),
  target_weekly_minutes INTEGER CHECK (target_weekly_minutes BETWEEN 0 AND 10080),
  max_weekly_minutes INTEGER CHECK (max_weekly_minutes BETWEEN 0 AND 10080),
  max_consecutive_days SMALLINT CHECK (max_consecutive_days BETWEEN 1 AND 14),
  allow_overtime BOOLEAN NOT NULL DEFAULT false,
  prefer_extra_hours BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (
    min_weekly_minutes IS NULL OR target_weekly_minutes IS NULL
    OR min_weekly_minutes <= target_weekly_minutes
  ),
  CHECK (
    target_weekly_minutes IS NULL OR max_weekly_minutes IS NULL
    OR target_weekly_minutes <= max_weekly_minutes
  ),
  UNIQUE (company_id, employee_id)
);

CREATE INDEX idx_employee_schedule_profiles_company
  ON employee_schedule_profiles(company_id);
```

Do not backfill a guessed target from `employment_type`. Existing employees remain `unconfirmed`. The frontend may suggest defaults, but a person must confirm the actual hour target.

Downgrade order: drop profile table, drop partial index/constraints, then drop added qualification columns.

## A2. Backend request models

Modify `server/app/matcha/models/scheduling/employee_schedule.py`:

```python
AvailabilityState = Literal["unconfirmed", "always_available", "windows"]
QualificationStatus = Literal["active", "training", "suspended"]


class EmployeeJobAssignmentInput(BaseModel):
    job_id: UUID
    is_primary: bool = False
    qualification_status: QualificationStatus = "active"
    qualified_from: date | None = None
    qualified_until: date | None = None
    notes: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _check_dates(self) -> "EmployeeJobAssignmentInput": ...


class EmployeeJobsReplace(BaseModel):
    assignments: list[EmployeeJobAssignmentInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _one_primary_and_unique_jobs(self) -> "EmployeeJobsReplace": ...


class EmployeeScheduleProfileUpdate(BaseModel):
    min_weekly_minutes: int | None = Field(None, ge=0, le=10080)
    target_weekly_minutes: int | None = Field(None, ge=0, le=10080)
    max_weekly_minutes: int | None = Field(None, ge=0, le=10080)
    max_consecutive_days: int | None = Field(None, ge=1, le=14)
    allow_overtime: bool = False
    prefer_extra_hours: bool = False

    @model_validator(mode="after")
    def _ordered_hours(self) -> "EmployeeScheduleProfileUpdate": ...
```

Extend `AvailabilityReplace` without breaking existing clients:

```python
class AvailabilityReplace(BaseModel):
    windows: list[AvailabilityWindow] = Field(default_factory=list, max_length=42)
    availability_state: Literal["always_available", "windows"] | None = None

    @model_validator(mode="after")
    def _derive_and_validate_state(self) -> "AvailabilityReplace":
        # Omitted state preserves old clients: [] means explicitly always
        # available; a non-empty list means window-limited.
        # `windows` requires >=1 row; `always_available` requires zero rows.
        ...
```

Comments must state that `unconfirmed` is a data-readiness state used by auto-assignment; it does not change legacy manual-assignment behavior.

## A3. Canonical services

Add `server/app/matcha/services/scheduling/schedule_profiles.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduleProfile:
    employee_id: UUID
    availability_state: str
    availability_confirmed_at: datetime | None
    min_weekly_minutes: int | None
    target_weekly_minutes: int | None
    max_weekly_minutes: int | None
    max_consecutive_days: int | None
    allow_overtime: bool
    prefer_extra_hours: bool


def effective_availability_state(
    requested_state: str | None,
    windows: Sequence[AvailabilityWindow],
) -> Literal["always_available", "windows"]:
    """Resolve backward-compatible PUT semantics; never return unconfirmed."""


async def fetch_schedule_profile(
    conn, *, company_id: UUID, employee_id: UUID,
) -> ScheduleProfile:
    """Return an explicit row or an in-memory unconfirmed default; do not mutate."""


async def upsert_schedule_profile(
    conn, *, company_id: UUID, employee_id: UUID,
    values: Mapping[str, object], actor_user_id: UUID | None,
) -> ScheduleProfile: ...


async def replace_availability_core(
    conn, *, company_id: UUID, employee_id: UUID,
    windows: Sequence[AvailabilityWindow], availability_state: str | None,
    actor_user_id: UUID | None, actor_kind: Literal["admin", "employee"],
) -> dict:
    """Replace windows and confirm the resulting state in one transaction owned by the caller."""


async def replace_employee_jobs_core(
    conn, *, company_id: UUID, employee_id: UUID,
    assignments: Sequence[EmployeeJobAssignmentInput], actor_user_id: UUID | None,
) -> list[dict]:
    """Replace one employee's qualification rows and materialize requirements for newly active jobs."""
```

Rules for `replace_employee_jobs_core()`:

1. Verify every job belongs to the company.
2. If a job has `location_id`, it must match the employee's `work_location_id`.
3. Lock existing qualification rows.
4. Preserve `created_at`/`created_by` for retained rows.
5. Delete removed rows, update retained rows, insert additions.
6. Call `materialize_job_requirements()` for newly active jobs.
7. Write one `schedule_job.employee_assignments.replace` audit entry with before/after job IDs; do not log one row per checkbox.

Refactor both current availability routes to call `replace_availability_core()`:

- `server/app/matcha/routes/employee_schedule/availability.py`
- `server/app/matcha/routes/employee_portal/schedule.py`

Keep the feature-dependency objects in `employee_portal/_shared.py`; do not recreate `require_feature()` closures.

## A4. API routes

Extend `server/app/matcha/routes/employee_schedule/jobs.py`:

```python
@router.get("/employees/{employee_id}/jobs")
async def get_employee_jobs(
    employee_id: UUID,
    current_user=Depends(require_admin_or_client),
) -> dict: ...


@router.put("/employees/{employee_id}/jobs")
async def replace_employee_jobs(
    employee_id: UUID,
    body: EmployeeJobsReplace,
    current_user=Depends(require_admin_or_client),
) -> dict: ...
```

Add to `server/app/matcha/routes/employee_schedule/availability.py`:

```python
@router.get("/profiles/{employee_id}")
async def get_employee_schedule_profile(...) -> dict: ...


@router.put("/profiles/{employee_id}")
async def update_employee_schedule_profile(
    employee_id: UUID,
    body: EmployeeScheduleProfileUpdate,
    current_user=Depends(require_admin_or_client),
) -> dict: ...
```

Response shape for the employee jobs endpoint:

```json
{
  "employee_id": "uuid",
  "assignments": [
    {
      "job_id": "uuid",
      "job_name": "Barista",
      "location_id": "uuid",
      "is_primary": true,
      "qualification_status": "active",
      "qualified_from": "2026-08-27",
      "qualified_until": null,
      "credential_requirements": []
    }
  ]
}
```

`PUT /jobs/{job_id}/employees` stays supported. Change its writer so retained rows preserve qualification metadata and new rows default to non-primary `active`. Removing the employee from a job may remove their primary assignment; the employee profile then shows “No primary job” rather than silently promoting another job.

## A5. Frontend

Modify `client/src/types/employeeSchedule.ts`:

```ts
export type AvailabilityState = 'unconfirmed' | 'always_available' | 'windows'
export type QualificationStatus = 'active' | 'training' | 'suspended'

export type EmployeeJobAssignment = {
  job_id: string
  job_name: string
  location_id: string | null
  is_primary: boolean
  qualification_status: QualificationStatus
  qualified_from: string | null
  qualified_until: string | null
  notes: string | null
  credential_requirements: JobCredentialRequirement[]
}

export type EmployeeScheduleProfile = {
  employee_id: string
  availability_state: AvailabilityState
  availability_confirmed_at: string | null
  min_weekly_minutes: number | null
  target_weekly_minutes: number | null
  max_weekly_minutes: number | null
  max_consecutive_days: number | null
  allow_overtime: boolean
  prefer_extra_hours: boolean
}
```

Add API functions to `client/src/api/employees/employeeSchedule.ts`:

```ts
export function fetchEmployeeJobs(employeeId: string): Promise<{ employee_id: string; assignments: EmployeeJobAssignment[] }>
export function replaceEmployeeJobs(employeeId: string, assignments: EmployeeJobAssignmentInput[]): Promise<...>
export function fetchEmployeeScheduleProfile(employeeId: string): Promise<EmployeeScheduleProfile>
export function updateEmployeeScheduleProfile(employeeId: string, payload: EmployeeScheduleProfileUpdate): Promise<EmployeeScheduleProfile>
```

Add `client/src/components/employees/EmployeeSchedulingPanel.tsx`:

- Job checklist with exactly one optional Primary radio.
- Status/effective-date controls for each checked job.
- Required credential summary inherited from each job.
- Min/target/max weekly-hour inputs displayed in hours but serialized as integer minutes.
- Recurring availability editor with explicit “Available anytime” vs “Use weekly windows.”
- “Not confirmed” badge until the employee/admin saves availability once.

Modify `client/src/pages/app/employees/EmployeeDetail.tsx`:

- Add `schedule` to the `Tab` union only when `employee_schedule` is enabled.
- Render `<EmployeeSchedulingPanel employeeId={employeeId!} />`.
- Keep `MinorCompliancePanel` visible; PR B will extend it rather than creating a second permit UI.

Do not add a new state/query library. Follow the existing controlled-input + `useState`/`useEffect` pattern.

## A6. Tests

Backend:

- `server/tests/employee_schedule/test_schedule_profile_models.py`
  - rejects two primary jobs;
  - rejects duplicate job IDs;
  - rejects inverted qualification dates;
  - rejects `min > target`, `target > max`;
  - derives `always_available` from an old-client empty PUT;
  - derives `windows` from a non-empty old-client PUT;
  - rejects `availability_state=windows` with no windows;
  - rejects `always_available` with windows.
- `server/tests/employee_schedule/test_schedule_profiles.py`
  - missing profile reads as unconfirmed without INSERT;
  - availability replacement and confirmation are atomic;
  - employee portal and admin routes call the same core;
  - tenant mismatch returns 404;
  - retained job metadata survives the job-centric checkbox endpoint;
  - newly active job materializes credential requirements;
  - location-scoped job cannot be assigned to an employee at another location;
  - primary unique violation becomes a clean 409/422, not 500.
- Extend `server/tests/employee_schedule/test_schedule_models.py` for new Pydantic models.
- Extend `server/tests/employee_portal/test_router_split_smoke.py` only if a new portal path is introduced. Merely changing response bodies does not change the snapshot.

Frontend:

- `client/src/components/employees/EmployeeSchedulingPanel.test.tsx`
  - loads jobs/profile/availability;
  - switches primary job without producing two primaries;
  - converts 32.5 hours to 1,950 minutes;
  - supports explicit always-available confirmation;
  - surfaces API validation errors without losing form state.
- Extend `client/src/components/employees/schedule-editor/ScheduleJobsTab.test.tsx` to prove job-centric roster saves do not require qualification metadata.

---

# PR B — structured minor work-permit restrictions

## B1. Migration

Create `server/alembic/versions/empsched17_minor_permit_restrictions.py`:

```python
revision = "empsched17"
down_revision = "empsched16"
```

Extend `employee_work_permits`:

```sql
ALTER TABLE employee_work_permits
  ADD COLUMN permit_number VARCHAR(120),
  ADD COLUMN issuing_authority VARCHAR(255),
  ADD COLUMN restrictions_confirmed BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN school_term_starts_on DATE,
  ADD COLUMN school_term_ends_on DATE,
  ADD COLUMN school_weekdays SMALLINT[] NOT NULL DEFAULT ARRAY[1,2,3,4,5]::SMALLINT[],
  ADD COLUMN notes TEXT;
```

Add checks for ordered school-term dates and weekday values in `0..6`.

Create:

```sql
CREATE TABLE employee_work_permit_restrictions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  permit_id UUID NOT NULL REFERENCES employee_work_permits(id) ON DELETE CASCADE,
  day_type VARCHAR(24) NOT NULL
    CHECK (day_type IN ('any', 'school_day', 'non_school_day', 'saturday', 'sunday')),
  earliest_start TIME,
  latest_end TIME,
  max_daily_minutes INTEGER CHECK (max_daily_minutes BETWEEN 1 AND 1440),
  max_weekly_minutes INTEGER CHECK (max_weekly_minutes BETWEEN 1 AND 10080),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (
    earliest_start IS NOT NULL OR latest_end IS NOT NULL
    OR max_daily_minutes IS NOT NULL OR max_weekly_minutes IS NOT NULL
  ),
  UNIQUE (permit_id, day_type)
);

CREATE INDEX idx_work_permit_restrictions_permit
  ON employee_work_permit_restrictions(permit_id);

CREATE TABLE employee_school_day_overrides (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  calendar_date DATE NOT NULL,
  is_school_day BOOLEAN NOT NULL,
  reason VARCHAR(500),
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (employee_id, calendar_date)
);
```

Existing permits remain usable for the current expiration gate, but `restrictions_confirmed=false` makes them ineligible for auto-assignment until reviewed. It does not retroactively remove manual assignments.

## B2. Models

Move the route-local `WorkPermitCreate` model out of `server/app/matcha/routes/employees/work_permits.py` into `server/app/matcha/models/scheduling/employee_schedule.py`:

```python
PermitDayType = Literal["any", "school_day", "non_school_day", "saturday", "sunday"]


class WorkPermitRestrictionInput(BaseModel):
    day_type: PermitDayType
    earliest_start: time | None = None
    latest_end: time | None = None
    max_daily_minutes: int | None = Field(None, ge=1, le=1440)
    max_weekly_minutes: int | None = Field(None, ge=1, le=10080)


class WorkPermitCreate(BaseModel):
    location_id: UUID
    issued_at: date | None = None
    expires_at: date
    confirmed_on_file: bool
    permit_number: str | None = Field(None, max_length=120)
    issuing_authority: str | None = Field(None, max_length=255)
    restrictions_confirmed: bool = False
    school_term_starts_on: date | None = None
    school_term_ends_on: date | None = None
    school_weekdays: list[Weekday] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    restrictions: list[WorkPermitRestrictionInput] = Field(default_factory=list, max_length=5)
    notes: str | None = Field(None, max_length=2000)
```

Validation:

- issue date ≤ expiration;
- school term start/end must be both null or correctly ordered;
- restriction day types unique;
- `restrictions_confirmed=false` may contain no restrictions;
- `restrictions_confirmed=true` with no rows explicitly means “permit reviewed; no permit-specific time limits beyond law.”

## B3. Pure rule engine

Add `server/app/matcha/services/scheduling/minor_work_permits.py`:

```python
@dataclass(frozen=True)
class PermitRestriction:
    day_type: str
    earliest_start: time | None
    latest_end: time | None
    max_daily_minutes: int | None
    max_weekly_minutes: int | None


@dataclass(frozen=True)
class PermitContext:
    permit_id: UUID
    issued_at: date | None
    expires_at: date
    restrictions_confirmed: bool
    school_term_starts_on: date | None
    school_term_ends_on: date | None
    school_weekdays: frozenset[int]
    restrictions: tuple[PermitRestriction, ...]
    school_day_overrides: Mapping[date, bool]


def is_school_day(on: date, context: PermitContext) -> bool: ...


def matching_restrictions(
    on: date, context: PermitContext,
) -> tuple[PermitRestriction, ...]:
    """Return `any` plus the applicable school/weekend class."""


def evaluate_permit_window(
    *, context: PermitContext, shift_start_local: datetime,
    shift_end_local: datetime, scheduled_day_minutes: int,
    scheduled_week_minutes: int,
) -> list[dict]:
    """Evaluate the strictest intersection of every matching permit restriction."""


async def minor_permit_schedule_violations(
    conn, company_id: UUID, *, employee_id: UUID,
    employee_age: int | None, location_id: UUID | None,
    starts_at: datetime, ends_at: datetime,
    exclude_shift_id: UUID | None = None,
) -> list[dict]: ...
```

Implementation rules:

- Return `[]` for an adult.
- Keep current missing/expired permit results in `schedule_eligibility_violations()`; this service adds restriction results after a valid permit is found.
- Reinterpret schedule wall-clock values using the location timezone.
- Count the entire scheduled span conservatively for minor daily/weekly caps. Do not subtract aggregate `break_minutes` until breaks are typed per assignment in PR E.
- Combine matching rows by taking the latest `earliest_start`, earliest `latest_end`, smallest daily cap, and smallest weekly cap.
- A shift crossing midnight is evaluated against both dates; it cannot evade a latest-end rule by ending the next day.
- Return stable codes: `minor_permit_restrictions_unconfirmed` (advisory/manual, hard auto-assign exclusion), `minor_permit_too_early`, `minor_permit_too_late`, `minor_permit_daily_hours`, `minor_permit_weekly_hours`.
- Restriction violations are `severity="block"`; `force=true` never bypasses them.

Call `minor_permit_schedule_violations()` from `check_shift_compliance()` in `server/app/matcha/services/scheduling/shift_compliance.py` after age and location context are known.

## B4. Canonical writer and routes

Add to `minor_work_permits.py`:

```python
async def record_work_permit_core(
    conn, *, company_id: UUID, employee_id: UUID,
    body: WorkPermitCreate, actor_user_id: UUID,
) -> dict:
    """Supersede the active location permit and insert its restriction rows atomically."""
```

Update both callers to use it:

- `server/app/matcha/routes/employees/work_permits.py`
- `server/app/matcha/services/scheduling/schedule_assistant_actions.py`

The service must not import a route module. The route owns HTTP errors and converts domain `ValueError`/not-found outcomes to 404/422.

Add endpoints to `work_permits.py`:

```python
@router.put("/{employee_id}/school-day-overrides/{calendar_date}")
async def put_school_day_override(...) -> dict: ...

@router.delete("/{employee_id}/school-day-overrides/{calendar_date}")
async def delete_school_day_override(...) -> dict: ...
```

Place these two-segment static paths so they cannot be shadowed by the employees package's `/{employee_id}` route pattern. Keep all reads company-scoped.

## B5. Frontend

Extend `client/src/components/employees/MinorCompliancePanel.tsx`:

- permit number and issuing authority;
- “I reviewed the permit’s work-hour restrictions” checkbox;
- school term date range and school weekdays;
- preset rows for school day, non-school day, Saturday, and Sunday;
- start/end and daily/weekly maximum inputs;
- explicit “No additional permit-specific restrictions” choice;
- permit history remains read-only and shows which restriction set was superseded.

Do not expose raw DOB after save. Continue showing only derived minor status.

## B6. Tests

- `server/tests/employee_schedule/test_minor_work_permits.py`
  - current valid permit at correct location passes;
  - different-location permit does not satisfy the gate;
  - issue date after shift date fails;
  - school term weekday is classified school day;
  - Saturday/Sunday rules win on their day;
  - date override changes school-day classification;
  - `any` and specific rules combine to the strictest result;
  - early start, late end, daily cap, and weekly cap block;
  - overnight shift cannot evade latest-end limit;
  - adult skips permit restrictions;
  - unconfirmed restrictions are advisory for manual review and an auto-assign exclusion;
  - confirmed empty restrictions means no extra permit rule, not missing data;
  - full scheduled span is counted conservatively;
  - superseding a permit and inserting restrictions is atomic;
  - hard block remains non-forceable through create, assign, move, swap approval, duplicate, template/chat execution.
- Extend `server/tests/employee_schedule/test_shift_compliance.py` for integration with the existing federal/state minor-hour evaluator.
- Extend `server/tests/employee_schedule/test_schedule_assistant_actions.py` to prove assistant and REST writers produce the same permit rows.
- `client/src/components/employees/MinorCompliancePanel.test.tsx` for restriction form validation and serialized minutes.

---

# PR C — week builder and deterministic schedule review

## C1. Template preview and duplicate-safe generation

Extend `GenerateFromWeekTemplate` in `employee_schedule.py`:

```python
class GenerateFromWeekTemplate(BaseModel):
    start_date: date
    end_date: date
    skip_existing: bool = True
```

Add pure helpers to `server/app/matcha/services/scheduling/schedule_rules.py`:

```python
def generated_shift_identity(
    *, location_id: UUID | None, job_id: UUID | None,
    starts_at: datetime, ends_at: datetime,
    role: str | None, department: str | None,
) -> tuple: ...


def classify_template_windows(
    generated: Sequence[GeneratedWindow], existing: Sequence[ExistingShift],
) -> TemplateGenerationPreview: ...
```

Identity normalizes whitespace/case for role and department and ignores cancelled shifts. It includes location, job, start, and end; two different jobs at the same time are not duplicates.

Add route to `server/app/matcha/routes/employee_schedule/week_templates.py`:

```python
@router.post("/week-templates/{week_template_id}/preview")
async def preview_week_template(
    week_template_id: UUID,
    body: GenerateFromWeekTemplate,
    current_user=Depends(require_admin_or_client),
) -> dict: ...
```

Response:

```json
{
  "would_create": 18,
  "would_skip": 2,
  "blocks": [{"block_id": "...", "name": "Barista open", "create": 5, "skip": 0}],
  "existing": [{"shift_id": "...", "reason": "same location/job/window"}],
  "compliance_warnings": []
}
```

Modify `generate_week_template_shifts()` in `shift_writes.py`:

```python
async def generate_week_template_shifts(
    conn, company_id: UUID, *, blocks: list,
    start_date: date, end_date: date, created_by: UUID,
    skip_existing: bool = True,
) -> dict:
```

Return `skipped_existing` and `per_block` in addition to the existing keys. Query existing identities once for the entire range; do not perform one duplicate query per generated shift.

No v1 “replace” mode. Managers may merge a template into drafts; published shifts are never deleted by template application.

## C2. Schedule review models

Add `server/app/matcha/models/scheduling/schedule_review.py` and export its models from `server/app/matcha/models/scheduling/__init__.py`:

```python
ReviewSeverity = Literal["block", "action_required", "advisory", "recommendation"]
ReviewCategory = Literal[
    "data_quality", "staffing", "eligibility", "compliance",
    "fair_workweek", "breaks", "coverage", "fairness",
]


class ScheduleReviewRequest(BaseModel):
    location_id: UUID
    week_start: date
    include_drafts: bool = True
    shift_ids: list[UUID] = Field(default_factory=list, max_length=500)


class SuggestedScheduleAction(BaseModel):
    kind: Literal[
        "open_shift", "assign_employee", "change_shift", "add_coverage",
        "plan_break", "renew_credential", "confirm_availability", "review_permit",
    ]
    payload: dict[str, object] = Field(default_factory=dict)


class ScheduleReviewIssue(BaseModel):
    issue_id: str
    code: str
    severity: ReviewSeverity
    category: ReviewCategory
    message: str
    shift_ids: list[UUID] = Field(default_factory=list)
    employee_ids: list[UUID] = Field(default_factory=list)
    statute: str | None = None
    can_override: bool = False
    suggested_actions: list[SuggestedScheduleAction] = Field(default_factory=list)
```

`issue_id` is a stable SHA-256-derived identifier over code + sorted subjects + relevant rule ID; it is not a random UUID. Stable IDs let the UI preserve dismissed/expanded state across refreshes.

## C3. Review service

Add `server/app/matcha/services/scheduling/schedule_review.py`:

```python
@dataclass(frozen=True)
class ScheduleReviewReport:
    status: Literal["ready", "needs_attention", "blocked"]
    location_id: UUID
    week_start: date
    generated_at: datetime
    snapshot_hash: str
    summary: Mapping[str, int]
    issues: tuple[ScheduleReviewIssue, ...]


async def build_schedule_snapshot(
    conn, *, company_id: UUID, location_id: UUID,
    week_start: date, include_drafts: bool,
) -> dict:
    """Load shifts, assignments, jobs, profiles, availability, requests, and rule timestamps in deterministic order."""


def hash_schedule_snapshot(snapshot: Mapping[str, object]) -> str:
    """Canonical JSON SHA-256; exclude generated timestamps and display-only names."""


async def review_schedule_week(
    conn, *, company_id: UUID, location_id: UUID,
    week_start: date, include_drafts: bool = True,
    shift_ids: Sequence[UUID] = (),
) -> ScheduleReviewReport: ...


def assert_publishable(report: ScheduleReviewReport) -> None:
    """Raise a domain error only when at least one issue has severity block."""
```

Review checks in PR C:

1. Location readiness and timezone/jurisdiction mapping.
2. Work shift missing a `job_id` (`action_required`, not legal block).
3. Open required slots (`advisory`; open shifts may still publish).
4. Current assignee no longer actively qualified for the job.
5. Credential/work-permit validity and minor restrictions.
6. Conflicts, approved time off, and recurring availability.
7. Existing shift compliance and break-rule mapping.
8. Fair Workweek preventive/exposure output already supported for the jurisdiction.
9. Unconfirmed employee availability (`action_required` only for auto-assign readiness).

Initial code/severity contract:

| Code | Severity | Override |
| --- | --- | --- |
| `schedule_location_not_ready` | `block` | no |
| `shift_job_missing` | `action_required` | not applicable |
| `shift_open_slots` | `advisory` | not applicable |
| `not_qualified_for_job` | `action_required` | yes, matching current manual semantics |
| `credential_missing` / `credential_expired` | `block` when the requirement is schedule-blocking | no |
| `minor_work_permit_*` restriction/validity code | `block` | no |
| `schedule_conflict` | `advisory` | yes, matching current manual semantics |
| `outside_availability` | `advisory` | yes, matching current manual semantics |
| `availability_unconfirmed` | `action_required` for auto-assign readiness; omitted from publish blocks | not applicable |
| `meal_break` / overtime / rest advisory | preserve severity returned by existing evaluator | preserve existing force behavior |
| `break_rules_unmapped` / `unmapped_state` | `advisory` | verify manually |
| Fair Workweek code | preserve the existing preventive evaluator's severity | preserve existing force/consent behavior |

Do not call Huume. Messages are deterministic templates. Sort issues by severity, date/time, code, employee ID.

For the first implementation, a 500-shift cap is acceptable and matches the assistant context cap. Load the week once; avoid route-level `fetch_shift_by_id()` loops. Existing compliance functions may still query supporting rule data, but add request-local caches for repeated employee/location lookups.

## C4. Review route and publish integration

Add `server/app/matcha/routes/employee_schedule/reviews.py`:

```python
router = APIRouter()


@router.post("/reviews/week")
async def review_week(
    body: ScheduleReviewRequest,
    current_user=Depends(require_admin_or_client),
) -> dict: ...
```

Include it in `server/app/matcha/routes/employee_schedule/__init__.py`.

Rollout:

1. Ship endpoint/UI in read-only shadow mode.
2. Compare its block results to existing write/publish gates in tests and pilot data.
3. Then call `review_schedule_week()` inside the publish transaction in `shifts.py` and reject only `severity=block` with:

```json
{
  "code": "schedule_review_blocked",
  "snapshot_hash": "...",
  "issues": []
}
```

Do not replace the existing publish checks; the review becomes an aggregate preflight and the current row-level gates remain defense in depth.

## C5. Frontend

Add API functions/types:

- `reviewScheduleWeek(payload)` in `client/src/api/employees/employeeSchedule.ts`.
- `ScheduleReviewReport`, `ScheduleReviewIssue`, and `SuggestedScheduleAction` in `client/src/types/employeeSchedule.ts`.

Add components:

- `client/src/components/employees/schedule-editor/ScheduleBuildPanel.tsx`
  - two cards: Apply template / Start from scratch;
  - template preview before Apply;
  - display create/skip counts and warnings;
  - applying reloads the editor and never publishes.
- `client/src/components/employees/schedule-editor/ScheduleReviewPanel.tsx`
  - grouped by Blocked, Action required, Warnings, Suggestions;
  - clicking an issue focuses its shift/employee;
  - renders citations but does not claim legal advice;
  - “Review again” always fetches current state.

Modify:

- `ScheduleEditorToolbar.tsx`: add `Build week` and `Review` controls.
- `ScheduleEditor.tsx`: mutually exclusive side panels for jobs/build/review/Huume.
- `useScheduleEditor.ts`: add `reviewing`, `reviewReport`, `reviewWeek()`; clear a report after any successful mutation because its snapshot is stale.
- `handlePublish()`: run review first; open the panel on any block; otherwise continue to the existing publish call.

## C6. Tests

- `server/tests/employee_schedule/test_template_preview.py`
  - same job/window is skipped;
  - different job at same time is created;
  - cancelled shift does not count as existing;
  - normalized role whitespace/case does not duplicate;
  - preview has zero writes;
  - generate and preview return matching create/skip counts;
  - one existing shift does not suppress unrelated block windows.
- `server/tests/employee_schedule/test_schedule_review.py`
  - report ordering and stable issue IDs;
  - hard credential/permit/minor issue blocks;
  - open slot is advisory only;
  - missing job is action-required only;
  - unconfirmed availability affects auto-assign readiness but not manual publish;
  - unmapped law is visible, never “clear”;
  - tenant/location mismatch returns 404;
  - cancelled shifts excluded;
  - selected shift IDs must all belong to requested location/week;
  - snapshot hash changes on shift, assignment, availability, job, credential, permit, or request change;
  - display-name-only changes do not alter hash.
- Extend `server/tests/employee_schedule/test_schedule_publish_eligibility.py` for aggregate block behavior.
- `ScheduleBuildPanel.test.tsx`, `ScheduleReviewPanel.test.tsx`, and `useScheduleEditor.test.tsx` for preview/apply, report invalidation, and publish interception.

---

# PR D — proposal-only auto-assignment

## D1. Dependency and solver boundary

Add a pinned OR-Tools version to `server/requirements.txt` after verifying Linux and macOS wheels in CI. Do not leave it unbounded. Import it only inside `assignment_solver.py` so ordinary API module import does not initialize solver machinery.

The solver receives plain immutable data and returns a plain result. It receives no DB connection and no PII/protected-trait fields.

## D2. Migration

Create `server/alembic/versions/empsched18_schedule_assignment_runs.py`:

```python
revision = "empsched18"
down_revision = "empsched17"
```

```sql
CREATE TABLE schedule_assignment_policies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
  default_full_time_target_minutes INTEGER
    CHECK (default_full_time_target_minutes BETWEEN 0 AND 10080),
  default_part_time_target_minutes INTEGER
    CHECK (default_part_time_target_minutes BETWEEN 0 AND 10080),
  rolling_fairness_weeks SMALLINT NOT NULL DEFAULT 8
    CHECK (rolling_fairness_weeks BETWEEN 1 AND 26),
  weekend_days SMALLINT[] NOT NULL DEFAULT ARRAY[0,6]::SMALLINT[],
  closing_time_threshold TIME,
  allow_overtime BOOLEAN NOT NULL DEFAULT false,
  objective_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (company_id, location_id)
);

CREATE TABLE schedule_assignment_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
  week_start DATE NOT NULL,
  status VARCHAR(20) NOT NULL
    CHECK (status IN ('building', 'proposed', 'applied', 'stale', 'failed', 'cancelled')),
  snapshot_hash VARCHAR(64) NOT NULL,
  solver_seed BIGINT NOT NULL,
  objective_weights JSONB NOT NULL,
  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  failure_reason TEXT,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  applied_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_schedule_assignment_runs_scope
  ON schedule_assignment_runs(company_id, location_id, week_start, created_at DESC);

CREATE TABLE schedule_assignment_run_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES schedule_assignment_runs(id) ON DELETE CASCADE,
  shift_id UUID NOT NULL REFERENCES schedule_shifts(id) ON DELETE CASCADE,
  employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  slot_ordinal SMALLINT NOT NULL CHECK (slot_ordinal >= 1),
  score INTEGER NOT NULL,
  score_breakdown JSONB NOT NULL,
  explanation JSONB NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'proposed'
    CHECK (status IN ('proposed', 'applied', 'skipped')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (run_id, shift_id, employee_id),
  UNIQUE (run_id, shift_id, slot_ordinal)
);

CREATE TABLE schedule_assignment_run_exclusions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES schedule_assignment_runs(id) ON DELETE CASCADE,
  shift_id UUID NOT NULL REFERENCES schedule_shifts(id) ON DELETE CASCADE,
  employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  reason_code VARCHAR(100) NOT NULL,
  reason_detail JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (run_id, shift_id, employee_id, reason_code)
);
```

Keep exclusions for audit/explanation, but manager list responses should default to aggregate counts. Fetching employee-level exclusions requires the run detail endpoint and manager authorization.

## D3. Models

Add `server/app/matcha/models/scheduling/assignment_runs.py`:

```python
class AssignmentRunCreate(BaseModel):
    location_id: UUID
    week_start: date
    shift_ids: list[UUID] = Field(default_factory=list, max_length=500)
    fill_open_slots_only: Literal[True] = True
    solver_seed: int | None = None


class AssignmentRunApply(BaseModel):
    item_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    expected_snapshot_hash: str = Field(..., min_length=64, max_length=64)


class AssignmentPolicyUpdate(BaseModel):
    default_full_time_target_minutes: int | None = Field(None, ge=0, le=10080)
    default_part_time_target_minutes: int | None = Field(None, ge=0, le=10080)
    rolling_fairness_weeks: int = Field(8, ge=1, le=26)
    weekend_days: list[Weekday] = Field(default_factory=lambda: [0, 6])
    closing_time_threshold: time | None = None
    allow_overtime: bool = False
    objective_weights: dict[str, int] = Field(default_factory=dict)


class AssignmentScoreBreakdown(BaseModel):
    coverage_reward: int
    target_hours_penalty: int
    overtime_penalty: int
    preference_penalty: int
    weekend_rotation_penalty: int
    closing_rotation_penalty: int
    tie_break: int
```

An empty `item_ids` on apply means all proposed items. The server never accepts arbitrary `(shift_id, employee_id)` pairs from the apply request; only persisted run items can be applied.

## D4. Candidate assembly

Add `server/app/matcha/services/scheduling/assignment_candidates.py`:

```python
@dataclass(frozen=True)
class Candidate:
    employee_id: UUID
    employment_type: str | None
    profile: ScheduleProfile
    current_week_minutes: int
    rolling_weekend_count: int
    rolling_closing_count: int
    stable_rotation_rank: int


@dataclass(frozen=True)
class CandidateEdge:
    shift_id: UUID
    employee_id: UUID
    eligible: bool
    exclusion_codes: tuple[str, ...]
    score_breakdown: Mapping[str, int]


async def build_candidate_matrix(
    conn, *, company_id: UUID, location_id: UUID,
    week_start: date, shift_ids: Sequence[UUID], solver_seed: int,
) -> CandidateMatrix: ...
```

Hard exclusions:

- inactive/offboarded employee;
- wrong work location;
- no active job qualification or qualification outside effective dates;
- missing/expired schedule-blocking credential;
- minor permit missing/expired/restriction violation/unconfirmed restrictions;
- approved time off or hard recurring unavailability;
- overlapping existing or proposed shift;
- profile max weekly minutes;
- non-overridable jurisdiction rule;
- `availability_state=unconfirmed`.

Auto-assign never uses a manual force path. A candidate excluded from the edge cannot be reintroduced by an objective weight.

Batch-query roster, qualifications, availability, requests, assignments, profiles, credentials, permits, and rolling eight-week assignment history. Do not issue one query per employee/shift pair.

## D5. Fairness objective

Add `server/app/matcha/services/scheduling/assignment_fairness.py`:

```python
DEFAULT_OBJECTIVE_WEIGHTS: Final = {
    "filled_slot": 100_000,
    "target_hour_deviation": 100,
    "overtime": 10_000,
    "preference": 500,
    "weekend_rotation": 100,
    "closing_rotation": 100,
    "tie_break": 1,
}


def score_candidate_edge(
    *, candidate: Candidate, shift: SolverShift,
    projected_minutes: int, policy: AssignmentPolicy,
) -> AssignmentScoreBreakdown: ...
```

Rules:

- Maximizing filled slots dominates every soft objective.
- Target-hour deviation uses the employee-confirmed target first. Otherwise it may use the client-configured location default for that employee's `employment_type`. If neither exists, mark the profile incomplete and exclude the employee from auto-assign. Do not ship built-in 40h/20h guesses.
- Overtime is excluded unless both policy and employee profile allow it; if allowed, it still carries a high penalty.
- Weekend/closing fairness is measured over a rolling eight weeks among comparable eligible employees.
- `weekend_days`, the rolling window, and the closing threshold come from the location policy. If no closing threshold is configured, the closing-rotation component is zero rather than guessed.
- Tie-breaking uses `HMAC(run_seed, employee_id + shift_id)` converted to a bounded integer. Persist the seed and breakdown.
- Names and database insertion order never participate.

Add `AssignmentPolicy` as code defaults in v1; a later admin-config table can expose weights. Persist the actual weights on every run so results remain explainable after defaults change.

## D6. Solver

Add `server/app/matcha/services/scheduling/assignment_solver.py`:

```python
@dataclass(frozen=True)
class SolverShift:
    shift_id: UUID
    starts_at: datetime
    ends_at: datetime
    open_slots: int
    job_id: UUID


@dataclass(frozen=True)
class ProposedAssignment:
    shift_id: UUID
    employee_id: UUID
    slot_ordinal: int
    score: int
    score_breakdown: Mapping[str, int]


@dataclass(frozen=True)
class AssignmentSolution:
    status: Literal["optimal", "feasible", "infeasible"]
    assignments: tuple[ProposedAssignment, ...]
    unfilled_slots: tuple[tuple[UUID, int], ...]
    objective_value: int


def solve_open_assignments(
    *, shifts: Sequence[SolverShift], edges: Sequence[CandidateEdge],
    existing_assignments: Sequence[ExistingAssignment],
    policy: AssignmentPolicy, seed: int,
) -> AssignmentSolution: ...
```

CP-SAT constraints:

1. At most one employee per shift slot.
2. One employee cannot take overlapping proposed shifts.
3. Existing assignments are fixed and count toward weekly minutes/consecutive days.
4. Projected weekly/max daily/minor caps cannot be exceeded.
5. A shift receives no more than its open slot count.
6. Every selected variable corresponds to an eligible `CandidateEdge`.
7. Deterministic worker count and seed; do not enable nondeterministic parallel search for v1.
8. Hard solve-time limit (for example, 10 seconds) returns the best feasible proposal with `status=feasible`; timeout does not apply writes.

## D7. Run service and apply semantics

Add `server/app/matcha/services/scheduling/assignment_runs.py`:

```python
async def create_assignment_run(
    conn, *, company_id: UUID, actor_user_id: UUID,
    request: AssignmentRunCreate,
) -> dict: ...


async def get_assignment_run(
    conn, *, company_id: UUID, run_id: UUID,
) -> dict: ...


async def apply_assignment_run(
    conn, *, company_id: UUID, actor_user_id: UUID,
    run_id: UUID, request: AssignmentRunApply,
) -> dict: ...
```

`create_assignment_run()`:

1. Validate location/week/shift scope.
2. Build and hash the current review snapshot.
3. Insert `building` run.
4. Build candidate matrix and solve.
5. Persist proposed items and exclusions.
6. Update run to `proposed` or `failed`.
7. Return proposal; no assignment writes.

`apply_assignment_run()` in one transaction:

1. Lock run `FOR UPDATE`; require `status=proposed`.
2. Rebuild current snapshot and compare both stored hash and request hash.
3. On mismatch set run `stale`, return 409 `schedule_assignment_run_stale`, and apply nothing.
4. Lock target shifts in deterministic ID order.
5. Re-run current tenant/location/employee/job/credential/permit/conflict/availability/compliance gates for every selected item.
6. If any selected item fails, roll back all and return 409 with item-level failures. Do not partially apply a reviewed plan.
7. Apply each item through `apply_assignment_core()` with:

```python
audit_details = {
    "source": "auto_assign",
    "assignment_run_id": str(run_id),
    "score_breakdown": item["score_breakdown"],
}
```

8. Mark items/run applied and commit.
9. Reconcile warning events after the transaction.

## D8. Routes

Add `server/app/matcha/routes/employee_schedule/assignment_runs.py` and include it in the package router:

```python
@router.post("/assignment-runs")
async def create_run(body: AssignmentRunCreate, ...) -> dict: ...

@router.get("/assignment-policy")
async def get_assignment_policy(location_id: UUID, ...) -> dict: ...

@router.put("/assignment-policy")
async def put_assignment_policy(
    location_id: UUID, body: AssignmentPolicyUpdate, ...,
) -> dict: ...

@router.get("/assignment-runs/{run_id}")
async def get_run(run_id: UUID, ...) -> dict: ...

@router.post("/assignment-runs/{run_id}/apply")
async def apply_run(run_id: UUID, body: AssignmentRunApply, ...) -> dict: ...

@router.post("/assignment-runs/{run_id}/cancel")
async def cancel_run(run_id: UUID, ...) -> dict: ...
```

Do not run the first version in Celery. A bounded 500-shift/10-second synchronous proposal keeps authorization, request cancellation, and UX simple. Move to Celery only if production timing proves necessary.

## D9. Frontend

Add:

- `client/src/components/employees/schedule-editor/AutoAssignPanel.tsx`
- `client/src/components/employees/schedule-editor/AssignmentExplanation.tsx`
- `client/src/hooks/employees/useAssignmentRun.ts`

UX:

1. “Auto assign” opens preflight.
2. Preflight lists incomplete employee profiles, missing location FT/PT defaults, unconfirmed availability, missing permits, and shifts with no job.
3. “Generate proposal” creates a run.
4. Grid renders proposed assignments as visually distinct ghosts; live assignments remain unchanged.
5. Manager may deselect individual proposed items.
6. “Apply selected assignments” sends item IDs + snapshot hash.
7. A stale 409 clears ghosts and offers “Generate again.”
8. After apply, reload week and open Review panel.

Explanation copy is assembled from stored score components and exclusion codes, not generated by Huume.

## D10. Tests

Pure solver tests in `server/tests/employee_schedule/test_assignment_solver.py`:

- fills all feasible slots;
- never selects an ineligible edge;
- never overlaps an employee;
- respects fixed existing assignments;
- respects weekly/max-consecutive/minor caps;
- leaves a slot open when no lawful candidate exists;
- target-hours objective changes the winner;
- weekend/closing rotation changes comparable winner;
- same seed/input produces byte-identical result;
- different seed changes only otherwise tied choices;
- filled-slot reward dominates fairness penalties;
- timeout returns feasible or failed proposal, never writes.

Candidate tests in `test_assignment_candidates.py`:

- every hard exclusion code listed above;
- no protected/demographic fields appear on `Candidate`;
- historical fairness only counts comparable eligible work;
- approved employee-request unavailability is hard;
- pending request is visible but not treated as approved time off;
- employee job effective dates are evaluated on shift date;
- unconfirmed availability and permit restrictions exclude auto-assign.
- employee target overrides the location employment-type default;
- location FT/PT default is used only when the matching client-authored value exists;
- missing employee target and missing matching location default produce `target_hours_unconfigured`.

Run/apply tests in `test_assignment_runs.py`:

- creation persists proposal but writes zero assignments/audits;
- run is tenant/location/week scoped;
- stale hash applies nothing and marks stale;
- one failed selected item rolls back the whole apply;
- apply uses `assignment.create` and run audit context;
- run cannot apply twice;
- cancelled/failed run cannot apply;
- subset application only applies requested persisted item IDs;
- arbitrary item ID or cross-run ID rejected;
- hard violation remains non-forceable;
- post-apply warning reconciliation runs only after commit.

Frontend tests cover preflight, ghost assignments, deselection, stale refresh, and successful apply.

---

# PR E — assignment-level breaks and floor coverage

## E1. Migration

Create `server/alembic/versions/empsched19_assignment_break_planning.py`:

```python
revision = "empsched19"
down_revision = "empsched18"
```

```sql
CREATE TABLE schedule_coverage_requirements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
  job_id UUID NOT NULL REFERENCES schedule_jobs(id) ON DELETE CASCADE,
  weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  min_active_staff SMALLINT NOT NULL CHECK (min_active_staff BETWEEN 1 AND 99),
  enforcement VARCHAR(24) NOT NULL DEFAULT 'action_required'
    CHECK (enforcement IN ('advisory', 'action_required')),
  is_active BOOLEAN NOT NULL DEFAULT true,
  notes TEXT,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (end_time > start_time),
  UNIQUE (location_id, job_id, weekday, start_time, end_time)
);

CREATE TABLE schedule_assignment_breaks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  shift_id UUID NOT NULL REFERENCES schedule_shifts(id) ON DELETE CASCADE,
  employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  kind VARCHAR(12) NOT NULL CHECK (kind IN ('meal', 'rest')),
  ordinal SMALLINT NOT NULL CHECK (ordinal >= 1),
  duration_minutes SMALLINT NOT NULL CHECK (duration_minutes BETWEEN 1 AND 240),
  earliest_at TIMESTAMPTZ,
  recommended_at TIMESTAMPTZ,
  deadline_at TIMESTAMPTZ,
  planned_starts_at TIMESTAMPTZ,
  planned_ends_at TIMESTAMPTZ,
  status VARCHAR(16) NOT NULL CHECK (status IN ('planned', 'waived')),
  rule_set_id UUID,
  citation TEXT,
  waiver_attestation_id UUID,
  source VARCHAR(20) NOT NULL CHECK (source IN ('engine', 'manager', 'huume')),
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (shift_id, employee_id, kind, ordinal),
  FOREIGN KEY (shift_id, employee_id)
    REFERENCES schedule_shift_assignments(shift_id, employee_id) ON DELETE CASCADE,
  CHECK (
    (status = 'waived' AND planned_starts_at IS NULL AND planned_ends_at IS NULL)
    OR
    (status = 'planned' AND planned_starts_at IS NOT NULL
      AND planned_ends_at IS NOT NULL AND planned_ends_at > planned_starts_at)
  )
);
```

Add indexes for `(company_id, shift_id)` and `(location_id, weekday)`.

Add proposal tables `schedule_break_plan_runs` / `schedule_break_plan_run_items` mirroring assignment-run status/snapshot semantics. Do not store proposed rows in `schedule_assignment_breaks`; that table is live state only.

## E2. Coverage and break services

Add `server/app/matcha/services/scheduling/schedule_coverage.py`:

```python
@dataclass(frozen=True)
class CoverageRequirement: ...

@dataclass(frozen=True)
class CoverageInterval:
    starts_at: datetime
    ends_at: datetime
    job_id: UUID
    required: int
    active: int
    deficit: int


def build_coverage_intervals(
    *, shifts: Sequence[CoverageShift],
    assignments: Sequence[CoverageAssignment],
    breaks: Sequence[PlannedBreak],
    requirements: Sequence[CoverageRequirement],
    bucket_minutes: int = 15,
) -> tuple[CoverageInterval, ...]: ...
```

Add `server/app/matcha/services/scheduling/break_planner.py`:

```python
@dataclass(frozen=True)
class BreakSlot: ...

@dataclass(frozen=True)
class ProposedBreak: ...

@dataclass(frozen=True)
class BreakPlanResult:
    breaks: tuple[ProposedBreak, ...]
    coverage_gaps: tuple[CoverageInterval, ...]
    unplaceable: tuple[BreakSlot, ...]


def required_break_slots(
    assignment_guidance: Sequence[AssignmentGuidance],
) -> tuple[BreakSlot, ...]: ...


def plan_breaks(
    *, slots: Sequence[BreakSlot],
    shifts: Sequence[CoverageShift],
    requirements: Sequence[CoverageRequirement],
    locked_breaks: Sequence[PlannedBreak],
    bucket_minutes: int = 15,
) -> BreakPlanResult: ...
```

Planner objectives, in order:

1. Every non-waived legal break placed before its deadline.
2. No interval below manager-authored minimum active coverage when a feasible placement exists.
3. Prefer recommended time, then spread simultaneous breaks.
4. Preserve manager-locked breaks.
5. Return unplaceable breaks/coverage gaps explicitly; never silently omit a requirement.

Reuse `resolve_break_rules()` / `evaluate_break_plan()` from existing break services. Do not duplicate legal rule parsing.

## E3. Routes

Add:

- `server/app/matcha/routes/employee_schedule/coverage.py`
- `server/app/matcha/routes/employee_schedule/break_plans.py`

Endpoints:

```text
GET    /coverage-requirements?location_id=...
PUT    /coverage-requirements?location_id=...     # full replacement
POST   /break-plan-runs                            # generate proposal
GET    /break-plan-runs/{run_id}
POST   /break-plan-runs/{run_id}/apply
PUT    /shifts/{shift_id}/assignments/{employee_id}/breaks/{break_id}
```

The direct break PUT is for manual adjustment. It validates the break remains within its permitted window; a coverage deficit returns forceable operational 409 only when the legal break itself remains valid. A late/out-of-window break is a hard 422.

Applying a break plan uses the same snapshot hash rules as assignment runs and is all-or-nothing.

## E4. Review and auto-assign integration

- Extend schedule review with `break_unplaceable`, `break_coverage_gap`, and `coverage_requirement_unfilled` issues.
- Extend assignment solver after PR E so coverage feasibility can reject a proposed solution that cannot place required breaks. Initial safe implementation: solve assignments, run break planner, and add a no-good constraint/retry for the conflicting employee/shift set up to a bounded retry count.
- Publish rejects only genuine hard break-law impossibility, not a merely preferred coverage recommendation. Operational coverage deficits are `action_required` or forceable advisory based on requirement configuration.

## E5. Frontend

Add:

- `CoverageRequirementsPanel.tsx` under schedule editor settings/jobs surface.
- `BreakTimeline.tsx` inside `ShiftInspector`.
- Break bars on `ShiftBlock` / `WeekTimeGrid` at sufficient zoom.
- Break-plan proposal mode in `ScheduleReviewPanel`.

Employee-facing schedule should show only that employee's planned break summary, not coworker coverage or legal-analysis internals.

## E6. Tests

- `test_schedule_coverage.py`: 15-minute interval math, overlapping shifts, job isolation, break subtraction, overnight windows, boundary equality.
- `test_break_planner.py`: deadline placement, recommended-time preference, coverage preservation, locked breaks, simultaneous break spreading, waiver, impossible coverage, deterministic output.
- `test_break_plan_runs.py`: proposal-only, stale rejection, atomic apply, manual edit legal window, coverage override audit.
- Extend `test_break_plans.py`, `test_schedule_review.py`, `test_assignment_solver.py`, daily digest tests, and portal schedule serialization tests.

---

# PR F — Huume as explainer and staged operator

## F1. Tool surface

Update the schedule allow-list in:

- `server/app/matcha/services/huume/tools.py`
- `server/app/matcha/services/huume/scope.py`
- `server/app/matcha/services/huume/prompt.py`
- the schedule-tool invariant comments in `SCHEDULE_HUUME_IMPLEMENTATION_PLAN.md` and scheduling `CLAUDE.md`.

Add tools:

```python
get_schedule_review(location_id, week_start, shift_ids=None)
get_assignment_run(run_id)
propose_assignment_run(location_id, week_start, shift_ids=None)
get_break_plan_run(run_id)
propose_break_plan(location_id, week_start, shift_ids=None)
```

Semantics:

- `get_*` is read-only.
- `propose_*` may create scratch proposal rows but never applies them.
- Applying an assignment/break run is a staged Huume action requiring a later manager confirmation, exactly like `propose_schedule_change`.
- Confirmation carries run ID + expected snapshot hash; a stale run produces a refusal to regenerate, never an automatic rerun-and-apply in the same turn.
- Huume relays deterministic issue messages/citations and may summarize them. It does not create new legal conclusions.

## F2. Action envelope

Extend `server/app/matcha/services/huume/actions.py` with action types:

```python
"schedule_assignment_run"
"schedule_break_plan_run"
```

Required payloads:

```python
schedule_assignment_run: ("run_id", "expected_snapshot_hash", "item_ids")
schedule_break_plan_run: ("run_id", "expected_snapshot_hash", "item_ids")
```

Execution delegates to `apply_assignment_run()` / `apply_break_plan_run()`. It does not reproduce validation or writes.

## F3. Prompt rules

Add explicit schedule instructions:

- inspect the review before recommending broad changes;
- distinguish legal block, required manager action, operational warning, and fairness recommendation;
- never say a proposal was applied until the confirm turn returns `applied`;
- never propose an unqualified/blocked employee as coverage;
- when no coverage requirement or demand signal exists, say floor flow is unconfigured rather than guessing;
- one schedule proposal attempt per turn remains in force.

## F4. Tests

- exact schedule tool allow-list includes the new tools and unrelated Huume tools remain excluded;
- read tool returns the deterministic report without mutation;
- proposal tool creates run and no assignments/breaks;
- confirmation delegates to canonical apply service;
- stale confirmation refuses and applies nothing;
- second proposal in the same turn is blocked by the existing schedule attempt cap;
- Huume prompt labels unmapped rules and absent coverage configuration honestly;
- editor reloads once after a successful applied run and not after proposal/read turns.

---

# 5. Required implementation comments

Comments/docstrings are required at the non-obvious safety boundaries below. Avoid narrating straightforward SQL or JSX.

- `empsched16`: explain why existing employees remain `availability_state='unconfirmed'` and why no FT/PT target is backfilled.
- `schedule_profiles.py`: explain that unconfirmed availability changes auto-assign readiness only; legacy manual scheduling still treats zero availability rows as fully available.
- `minor_work_permits.py`: explain UTC-wall-clock reinterpretation, conservative full-span hour counting, and strictest-rule intersection.
- `schedule_review.py`: explain why the snapshot hash excludes display names/timestamps but includes every eligibility input.
- `assignment_candidates.py`: label the hard-filter boundary; anything excluded here can never be restored by a solver weight.
- `assignment_fairness.py`: state the prohibited inputs and why a persisted seeded tie-break is used instead of name/ID order.
- `assignment_solver.py`: document objective priority and deterministic single-worker settings.
- `assignment_runs.py`: explain all-or-nothing stale protection and why apply calls the existing assignment core instead of inserting directly.
- `break_planner.py`: state that an unplaceable break is returned explicitly and never dropped to improve the apparent coverage score.
- Huume tool/action code: state that run creation is proposal scratch state and that only a later confirmed action may apply it.

# 6. Shared error contract

Every new domain error uses a structured `detail` object:

```json
{
  "code": "stable_snake_case_code",
  "message": "Manager-readable sentence",
  "can_override": false,
  "shift_ids": [],
  "employee_ids": [],
  "violations": []
}
```

Status usage:

- `404`: tenant-scoped resource absent or outside caller scope.
- `409`: stale proposal, already-applied run, forceable operational conflict, or current-state conflict.
- `422`: invalid payload or non-overridable legal/eligibility block.
- Never return 200 with `ok=false` for a failed apply.

Add the new codes to `client/src/pages/app/employees/scheduleConflicts.ts` only when they support a deliberate manager override. Stale/hard codes get dedicated UI, not `window.confirm()`.

# 7. Audit contract

New audit actions:

```text
schedule_job.employee_assignments.replace
schedule_profile.update
availability.update                       # preserve existing action
employee.work_permit.record               # preserve existing action
schedule_review.run
assignment_run.create
assignment_run.apply
assignment_run.cancel
break_plan_run.create
break_plan_run.apply
coverage_requirements.replace
assignment.break.update
```

Actual assignment writes still emit `assignment.create`. Run-level audit supplements rather than replaces assignment audit.

Do not put protected traits, DOB, permit numbers, or credential document contents into solver explanations or audit JSON. Permit audit may reference the permit row ID and restriction categories.

# 8. Verification gates per PR

Backend focused suite:

```bash
cd server
./venv/bin/python -m pytest tests/employee_schedule/ -q --disable-warnings
./venv/bin/python -m pytest tests/huume/ tests/employee_portal/ -q --disable-warnings
./venv/bin/python -m compileall -q app/matcha/services/scheduling app/matcha/routes/employee_schedule app/matcha/models/scheduling
./venv/bin/alembic heads
```

Frontend:

```bash
cd client
npx tsc -p tsconfig.app.json --noEmit
npm test -- --run \
  src/components/employees/schedule-editor \
  src/components/employees/EmployeeSchedulingPanel.test.tsx \
  src/components/employees/MinorCompliancePanel.test.tsx \
  src/hooks/employees/useScheduleEditor.test.tsx
```

Repo guards:

```bash
git diff --check
! rg -n "from app\.matcha\.routes|import app\.matcha\.routes" \
  server/app/matcha/services/scheduling
```

Before enabling auto-assignment for a pilot:

1. Run solver in proposal-only shadow mode for at least two scheduling cycles.
2. Compare fill rate, target-hour deviation, weekend/closing distribution, overtime, manual edits, and exclusion reasons.
3. Verify no protected-trait fields enter solver inputs or persisted explanations.
4. Review every hard legal rule/citation used by the pilot location.
5. Confirm employee availability and minor permit restrictions are complete.
6. Keep Apply manager-initiated; do not schedule a background auto-apply worker.

# 9. Definition of done

- A client can define jobs/credential rules and edit an employee's primary/additional qualified jobs from that employee's profile.
- Auto-assignment refuses employees with unconfirmed availability or incomplete minor-permit restrictions.
- A minor cannot be manually or automatically scheduled outside a hard permit restriction.
- The full editor clearly offers Apply template and Start from scratch.
- Review Schedule returns deterministic, stable, categorized issues and is re-run at publish/apply time.
- Auto-assign creates a persisted, explainable, deterministic proposal and never writes before confirmation.
- Proposal application is atomic, stale-safe, tenant-safe, and uses existing assignment writers/audit names.
- Break plans are per employee assignment, respect legal windows, and show floor-coverage gaps.
- Huume explains and stages; deterministic services decide and write.
