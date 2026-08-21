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

# ISO-ish weekday integers: 0=Sunday .. 6=Saturday.
Weekday = Literal[0, 1, 2, 3, 4, 5, 6]


class ShiftCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    role: Optional[str] = Field(None, max_length=150)
    department: Optional[str] = Field(None, max_length=100)
    location_id: Optional[UUID] = None
    break_minutes: int = Field(0, ge=0, le=1440)
    required_staff: int = Field(1, ge=1, le=99)
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    # Which job this shift is (Box Office, Concessions, ...) — None means
    # ungated, anyone can be assigned. Enforced (forceable) at assignment
    # time, not here.
    job_id: Optional[UUID] = None
    # Employees to assign up front (optional).
    employee_ids: list[UUID] = Field(default_factory=list)
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
    break_minutes: Optional[int] = Field(None, ge=0, le=1440)
    required_staff: Optional[int] = Field(None, ge=1, le=99)
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    status: Optional[ShiftStatus] = None
    job_id: Optional[UUID] = None

    _utc = field_validator("starts_at", "ends_at")(_as_utc)

    @model_validator(mode="after")
    def _check_window(self) -> "ShiftUpdate":
        # Only when the caller sent both — a one-sided retime is checked against
        # the stored value in the route (see shifts.py:update_shift).
        if self.starts_at is not None and self.ends_at is not None:
            if self.ends_at <= self.starts_at:
                raise ValueError("ends_at must be after starts_at")
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


class JobUpdate(BaseModel):
    """True PATCH on the job itself — the qualified list has its own
    replace endpoint (PUT /jobs/{id}/employees), not resubmitted here."""

    name: Optional[str] = Field(None, min_length=1, max_length=150)
    location_id: Optional[UUID] = None
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)


class JobEmployeesReplace(BaseModel):
    """Whole-list replace — the UI is a checkbox roster, so a diffing
    add/remove pair would just re-derive this on the client anyway."""

    employee_ids: list[UUID] = Field(default_factory=list, max_length=500)


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
    unavailable_start: Optional[date] = None
    unavailable_end: Optional[date] = None
    reason: Optional[str] = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _check_shape(self) -> "ScheduleRequestCreate":
        if self.request_type in ("swap", "drop", "pickup") and self.shift_id is None:
            raise ValueError("shift_id is required for swap/drop/pickup requests")
        if self.request_type == "swap" and self.target_employee_id is None:
            raise ValueError("target_employee_id is required for swap requests")
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
    becomes exactly this list). Empty list = clear = fully available."""

    windows: list[AvailabilityWindow] = Field(default_factory=list, max_length=42)

    @model_validator(mode="after")
    def _check_overlaps(self) -> "AvailabilityReplace":
        by_day: dict[int, list[AvailabilityWindow]] = {}
        for w in self.windows:
            by_day.setdefault(w.weekday, []).append(w)
        for day, ws in by_day.items():
            ws.sort(key=lambda w: w.start_time)
            for a, b in zip(ws, ws[1:]):
                if b.start_time < a.end_time:
                    raise ValueError(f"overlapping windows on weekday {day}")
        return self


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
