"""Employee-schedule request models (feature `employee_schedule`).

Shifts, assignments, templates, and employee-initiated swap/unavailability
requests. Response shapes are assembled as plain dicts in the route layer
(see routes/employee_schedule/_shared.py:serialize_shift).
"""

from datetime import date, datetime, time, timezone
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize an incoming datetime to UTC.

    The columns are timestamptz and the whole surface is a UTC wall-clock (what
    an admin types is what an employee sees). A client that omits the offset
    would otherwise produce a naive datetime, and comparing it against the
    tz-aware value read back from the DB raises TypeError → 500 instead of a
    clean 422.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


ShiftStatus = Literal["draft", "published", "cancelled"]
ShiftKind = Literal["work", "training"]
AssignmentStatus = Literal["assigned", "confirmed", "declined"]
RequestType = Literal["swap", "drop", "pickup", "unavailable"]
RequestStatus = Literal[
    "pending", "awaiting_counterparty", "awaiting_manager", "approved", "denied", "cancelled"
]
RequestDecision = Literal["approved", "denied"]
AvailabilityState = Literal["unconfirmed", "always_available", "windows"]
QualificationStatus = Literal["active", "training", "suspended"]
ScheduleAutomationCadence = Literal["weekly", "once"]

# ISO-ish weekday integers: 0=Sunday .. 6=Saturday.
Weekday = Literal[0, 1, 2, 3, 4, 5, 6]


class ShiftCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    role: Optional[str] = Field(None, max_length=150)
    department: Optional[str] = Field(None, max_length=100)
    location_id: Optional[UUID] = None
    break_minutes: int = Field(0, ge=0, le=1440)
    # Distinguish an intentional manager value from the legacy clients that
    # always serialized their zero default.  Missing mode remains compatible
    # with those clients and is treated as automatic by the route.
    break_mode: Optional[Literal["auto", "manual"]] = None
    required_staff: int = Field(1, ge=1, le=99)
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    # Which job this shift is (Box Office, Concessions, ...) — None means
    # ungated, anyone can be assigned. Enforced (forceable) at assignment
    # time, not here.
    job_id: Optional[UUID] = None
    # Employees to assign up front (optional).
    employee_ids: list[UUID] = Field(default_factory=list, max_length=99)
    # 'training' ties the shift to a training_requirement — assigning an
    # employee creates/accelerates their training record instead of (not in
    # addition to) matching scheduled_role rules. Immutable after create
    # (no equivalent field on ShiftUpdate) — flipping kind mid-flight would
    # leave existing training records' provenance ambiguous.
    kind: ShiftKind = "work"
    training_requirement_id: Optional[UUID] = None

    _utc = field_validator("starts_at", "ends_at")(_as_utc)

    @model_validator(mode="after")
    def _check_window(self) -> "ShiftCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self

    @model_validator(mode="after")
    def _check_kind(self) -> "ShiftCreate":
        if self.kind == "training" and self.training_requirement_id is None:
            raise ValueError("training shifts require training_requirement_id")
        if self.kind == "work" and self.training_requirement_id is not None:
            raise ValueError("training_requirement_id is only valid on training shifts")
        return self


class ShiftUpdate(BaseModel):
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    role: Optional[str] = Field(None, max_length=150)
    department: Optional[str] = Field(None, max_length=100)
    location_id: Optional[UUID] = None
    # Omission means "leave unchanged"; explicit null is not a valid stored
    # value.  Keeping the annotation non-null also makes OpenAPI tell clients
    # the truth while exclude_unset still distinguishes an omitted field.
    break_minutes: int = Field(default=None, ge=0, le=1440)  # type: ignore[assignment]
    break_mode: Optional[Literal["auto", "manual"]] = None
    required_staff: Optional[int] = Field(None, ge=1, le=99)
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    status: Optional[ShiftStatus] = None
    job_id: Optional[UUID] = None

    _utc = field_validator("starts_at", "ends_at")(_as_utc)

    @field_validator("break_minutes", mode="before")
    @classmethod
    def _reject_null_break_minutes(cls, value):
        if value is None:
            raise ValueError("break_minutes cannot be null")
        return value

    @model_validator(mode="after")
    def _check_window(self) -> "ShiftUpdate":
        # Only when the caller sent both — a one-sided retime is checked against
        # the stored value in the route (see shifts.py:update_shift).
        if self.starts_at is not None and self.ends_at is not None:
            if self.ends_at <= self.starts_at:
                raise ValueError("ends_at must be after starts_at")
        if self.break_mode == "manual" and self.break_minutes is None:
            raise ValueError("manual break_mode requires break_minutes")
        return self


class AssignmentCreate(BaseModel):
    employee_id: UUID


class AssignmentNoteUpdate(BaseModel):
    note: Optional[str] = Field(None, max_length=2000)
    visible_to_employee: bool = True
    include_in_location_digest: bool = True
    send_employee_notice: bool = True


class MealWaiverAttestationUpdate(BaseModel):
    on_file: bool
    effective_from: Optional[date] = None
    note: Optional[str] = Field(None, max_length=1000)


class MealWaiverAttestationResponse(BaseModel):
    """The current effective meal-break-waiver attestation for an employee."""

    employee_id: UUID
    on_file: bool
    attested: bool
    effective_from: Optional[date] = None
    confirmed_at: Optional[datetime] = None
    note: Optional[str] = None


class EligibilityCaseDecision(BaseModel):
    decision: Literal["remove", "keep"]
    acknowledgement_confirmed: bool = False
    acknowledgement_note: Optional[str] = Field(None, max_length=2000)


class AssignmentMove(BaseModel):
    employee_id: UUID
    from_shift_id: UUID
    to_shift_id: UUID

    @model_validator(mode="after")
    def _different_shifts(self) -> "AssignmentMove":
        if self.from_shift_id == self.to_shift_id:
            raise ValueError("source and destination shifts must differ")
        return self


class PublishRange(BaseModel):
    """Bulk-publish every draft shift whose start falls in [start, end)."""

    start: datetime
    end: datetime
    # Scope to one location, matching whichever location's week the caller is
    # looking at — omitted publishes across every location (used by the
    # portal / non-location-scoped callers).
    location_id: Optional[UUID] = None

    _utc = field_validator("start", "end")(_as_utc)

    @model_validator(mode="after")
    def _check_window(self) -> "PublishRange":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class BlockCreate(BaseModel):
    """One shift-block inside a week template. Same shape as a standalone
    template minus location_id (inherited from the parent, never diverges)."""

    name: str = Field(..., min_length=1, max_length=150)
    role: Optional[str] = Field(None, max_length=150)
    department: Optional[str] = Field(None, max_length=100)
    start_time: time
    end_time: time
    break_minutes: int = Field(0, ge=0, le=1440)
    required_staff: int = Field(1, ge=1, le=99)
    days_of_week: list[Weekday] = Field(default_factory=list)
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    job_id: Optional[UUID] = None


class BlockUpdate(BaseModel):
    """True PATCH — same fields as BlockCreate, all optional."""

    name: Optional[str] = Field(None, min_length=1, max_length=150)
    role: Optional[str] = Field(None, max_length=150)
    department: Optional[str] = Field(None, max_length=100)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: Optional[int] = Field(None, ge=0, le=1440)
    required_staff: Optional[int] = Field(None, ge=1, le=99)
    days_of_week: Optional[list[Weekday]] = None
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    job_id: Optional[UUID] = None


class JobCreate(BaseModel):
    """A job employees can be qualified for (Box Office, Concessions,
    Ushers, ...). Shifts/blocks point at a job via job_id; assignment is
    gated (forceable) to employees on that job's qualified list."""

    name: str = Field(..., min_length=1, max_length=150)
    location_id: Optional[UUID] = None
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    employee_ids: list[UUID] = Field(default_factory=list, max_length=500)
    credential_grace_days: Optional[int] = Field(None, ge=0, le=365)
    credential_requirements: list["JobCredentialRequirementInput"] = Field(default_factory=list, max_length=100)


class JobUpdate(BaseModel):
    """True PATCH on the job itself — the qualified list has its own
    replace endpoint (PUT /jobs/{id}/employees), not resubmitted here."""

    name: Optional[str] = Field(None, min_length=1, max_length=150)
    location_id: Optional[UUID] = None
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    credential_grace_days: Optional[int] = Field(None, ge=0, le=365)


class JobCredentialRequirementInput(BaseModel):
    credential_type_id: UUID
    is_required: bool = True
    schedule_blocking: bool = True
    notes: Optional[str] = Field(None, max_length=2000)


class JobCredentialRequirementsReplace(BaseModel):
    requirements: list[JobCredentialRequirementInput] = Field(default_factory=list, max_length=100)


class JobEmployeesReplace(BaseModel):
    """Whole-list replace — the UI is a checkbox roster, so a diffing
    add/remove pair would just re-derive this on the client anyway."""

    employee_ids: list[UUID] = Field(default_factory=list, max_length=500)


class EmployeeJobAssignmentInput(BaseModel):
    job_id: UUID
    is_primary: bool = False
    qualification_status: QualificationStatus = "active"
    qualified_from: Optional[date] = None
    qualified_until: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _check_qualification_dates(self) -> "EmployeeJobAssignmentInput":
        if self.qualified_from and self.qualified_until and self.qualified_until < self.qualified_from:
            raise ValueError("qualified_until must be on or after qualified_from")
        if self.is_primary and self.qualification_status != "active":
            raise ValueError("only an active qualification can be primary")
        return self


class EmployeeJobsReplace(BaseModel):
    assignments: list[EmployeeJobAssignmentInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _check_jobs(self) -> "EmployeeJobsReplace":
        job_ids = [job.job_id for job in self.assignments]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("job assignments must be unique")
        if sum(job.is_primary for job in self.assignments) > 1:
            raise ValueError("an employee can have only one primary job")
        return self


class EmployeeScheduleProfileUpdate(BaseModel):
    min_weekly_minutes: Optional[int] = Field(None, ge=0, le=10080)
    target_weekly_minutes: Optional[int] = Field(None, ge=0, le=10080)
    max_weekly_minutes: Optional[int] = Field(None, ge=0, le=10080)
    max_consecutive_days: Optional[int] = Field(None, ge=1, le=14)
    allow_overtime: bool = False
    prefer_extra_hours: bool = False

    @model_validator(mode="after")
    def _ordered_hours(self) -> "EmployeeScheduleProfileUpdate":
        if self.min_weekly_minutes is not None and self.target_weekly_minutes is not None:
            if self.min_weekly_minutes > self.target_weekly_minutes:
                raise ValueError("min_weekly_minutes cannot exceed target_weekly_minutes")
        if self.target_weekly_minutes is not None and self.max_weekly_minutes is not None:
            if self.target_weekly_minutes > self.max_weekly_minutes:
                raise ValueError("target_weekly_minutes cannot exceed max_weekly_minutes")
        if self.min_weekly_minutes is not None and self.max_weekly_minutes is not None:
            if self.min_weekly_minutes > self.max_weekly_minutes:
                raise ValueError("min_weekly_minutes cannot exceed max_weekly_minutes")
        return self


JobCreate.model_rebuild()


class WeekTemplateCreate(BaseModel):
    """A named, reusable week of shift blocks. Location is set once here and
    inherited by every block (block-level location_id is a DB implementation
    detail, not exposed on this payload)."""

    name: str = Field(..., min_length=1, max_length=150)
    location_id: Optional[UUID] = None
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    blocks: list[BlockCreate] = Field(default_factory=list, max_length=40)


class WeekTemplateUpdate(BaseModel):
    """True PATCH on the parent's own fields only — blocks are managed via
    their own add/update/delete endpoints, not by resubmitting the list."""

    name: Optional[str] = Field(None, min_length=1, max_length=150)
    location_id: Optional[UUID] = None
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)


class WeekTemplateBlockReplace(BaseModel):
    """A complete block submitted as part of a template-wide reconciliation.

    ``id`` identifies an existing child to update.  Omitted IDs are inserted;
    existing children omitted from the list are removed by the route. Only
    fields owned by the week-template editor are accepted here, so saving the
    visible form cannot overwrite richer block metadata managed elsewhere.
    """

    id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=150)
    role: Optional[str] = Field(None, max_length=150)
    start_time: time
    end_time: time
    break_minutes: int = Field(0, ge=0, le=1440)
    required_staff: int = Field(1, ge=1, le=99)
    days_of_week: list[Weekday] = Field(default_factory=list)


class WeekTemplateReplace(BaseModel):
    """Atomically replace a template's editable block list.

    This is deliberately separate from ``WeekTemplateUpdate``: the latter is a
    true PATCH for parent fields, while this payload represents the whole list
    rendered by the editor.
    """

    name: str = Field(..., min_length=1, max_length=150)
    blocks: list[WeekTemplateBlockReplace] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def _check_unique_block_ids(self) -> "WeekTemplateReplace":
        block_ids = [block.id for block in self.blocks if block.id is not None]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("template block ids must be unique")
        return self


class GenerateFromWeekTemplate(BaseModel):
    """Materialize concrete shifts from every block in a week template across
    a date range, all sharing one series_id.

    Every date in [start_date, end_date] whose weekday is in a block's
    days_of_week gets one draft shift from that block. Overnight blocks
    (end_time <= start_time) roll ends_at to the next calendar day.
    """

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _check_range(self) -> "GenerateFromWeekTemplate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 186:
            raise ValueError("date range too large (max ~6 months)")
        return self


class ScheduleRequestCreate(BaseModel):
    """Employee-initiated request (created from the portal)."""

    request_type: RequestType
    shift_id: Optional[UUID] = None
    target_employee_id: Optional[UUID] = None
    counter_shift_id: Optional[UUID] = None
    unavailable_start: Optional[date] = None
    unavailable_end: Optional[date] = None
    reason: Optional[str] = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _check_shape(self) -> "ScheduleRequestCreate":
        if self.request_type in ("swap", "drop", "pickup") and self.shift_id is None:
            raise ValueError("shift_id is required for swap/drop/pickup requests")
        if self.request_type == "swap" and self.target_employee_id is None:
            raise ValueError("target_employee_id is required for swap requests")
        if self.request_type == "swap" and self.counter_shift_id is None:
            raise ValueError("counter_shift_id is required for swap requests")
        if self.request_type == "swap" and self.counter_shift_id == self.shift_id:
            raise ValueError("a swap needs two different shifts")
        if self.request_type != "swap" and self.counter_shift_id is not None:
            raise ValueError("counter_shift_id is only valid for swap requests")
        if self.request_type == "unavailable":
            if self.unavailable_start is None or self.unavailable_end is None:
                raise ValueError("unavailable_start and unavailable_end are required")
            if self.unavailable_end < self.unavailable_start:
                raise ValueError("unavailable_end must be on or after unavailable_start")
        return self


class CounterpartyAccept(BaseModel):
    """Acceptance of an offer; swaps also identify the shift being traded."""

    counter_shift_id: Optional[UUID] = None


class RequestReview(BaseModel):
    decision: RequestDecision
    review_notes: Optional[str] = Field(None, max_length=2000)
    # Approve a swap even if the target employee has an overlapping shift.
    force: bool = False


class AvailabilityWindow(BaseModel):
    weekday: Weekday
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _check_order(self) -> "AvailabilityWindow":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AvailabilityReplace(BaseModel):
    """Full-replacement weekly availability (PUT semantics — the stored set
    becomes exactly this list). Legacy callers may omit state: an empty list
    then explicitly means always available, preserving the original API.

    ``unconfirmed`` is a data-readiness state for future auto-assignment. It
    does not change legacy/manual assignment behavior and cannot be submitted
    as a confirmed availability choice.
    """

    availability_state: Optional[Literal["always_available", "windows"]] = None
    windows: list[AvailabilityWindow] = Field(default_factory=list, max_length=42)

    @model_validator(mode="after")
    def _check_overlaps(self) -> "AvailabilityReplace":
        if self.availability_state == "windows" and not self.windows:
            raise ValueError("windows state requires at least one availability window")
        if self.availability_state == "always_available" and self.windows:
            raise ValueError("always_available state cannot include availability windows")
        by_day: dict[int, list[AvailabilityWindow]] = {}
        for w in self.windows:
            by_day.setdefault(w.weekday, []).append(w)
        for day, ws in by_day.items():
            ws.sort(key=lambda w: w.start_time)
            for a, b in zip(ws, ws[1:]):
                if b.start_time < a.end_time:
                    raise ValueError(f"overlapping windows on weekday {day}")
        return self


class EmployeeSchedulingDetailsUpdate(BaseModel):
    """Atomic employee scheduling-details save used by the admin profile panel.

    ``jobs`` is optional so an unrelated profile/availability save can preserve
    stale location assignments until an admin deliberately resolves them.
    """

    jobs: Optional[EmployeeJobsReplace] = None
    availability: AvailabilityReplace
    profile: EmployeeScheduleProfileUpdate


class DuplicateShift(BaseModel):
    """Copy one shift onto other calendar dates (drafts)."""

    target_dates: list[date] = Field(..., min_length=1, max_length=31)
    include_assignments: bool = True

    @model_validator(mode="after")
    def _dedupe(self) -> "DuplicateShift":
        self.target_dates = sorted(set(self.target_dates))
        return self


class ScheduleChatMessage(BaseModel):
    """One turn in the schedule editor's staged assistant."""

    message: str = Field(..., min_length=1, max_length=2000)
    week_start: Optional[date] = None
    location_id: Optional[UUID] = None
    edit_published: bool = False
    existing_proposal_id: Optional[UUID] = None


class ScheduleChatApply(BaseModel):
    """The editor's explicit apply decision."""

    as_draft: bool = True
    edit_published: bool = False


class ScheduleVoiceTranscript(BaseModel):
    """Verbatim voice turn plus deterministic confirm/cancel classification."""

    available: bool
    transcript: Optional[str] = None
    command: Literal["confirm", "cancel", "other"] = "other"
    model: Optional[str] = None


class ScheduleAutomationRuleUpsert(BaseModel):
    """One review-only Huume generation cadence for a store location."""

    enabled: bool = True
    cadence: ScheduleAutomationCadence = "weekly"
    week_template_id: UUID
    run_weekday: Optional[Weekday] = None
    run_date: Optional[date] = None
    run_time: time
    target_weeks_ahead: Optional[int] = Field(None, ge=1, le=8)
    target_week_start: Optional[date] = None

    @model_validator(mode="after")
    def _check_cadence_shape(self) -> "ScheduleAutomationRuleUpsert":
        if self.cadence == "weekly":
            if self.run_weekday is None or self.target_weeks_ahead is None:
                raise ValueError("weekly schedules require run_weekday and target_weeks_ahead")
            if self.run_date is not None or self.target_week_start is not None:
                raise ValueError("weekly schedules cannot include one-time dates")
        else:
            if self.run_date is None or self.target_week_start is None:
                raise ValueError("one-time schedules require run_date and target_week_start")
            if self.run_weekday is not None or self.target_weeks_ahead is not None:
                raise ValueError("one-time schedules cannot include weekly fields")
            if self.target_week_start.weekday() != 6:
                raise ValueError("target_week_start must be a Sunday")
        return self
