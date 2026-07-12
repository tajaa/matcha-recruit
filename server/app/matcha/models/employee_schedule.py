"""Employee-schedule request models (feature `employee_schedule`).

Shifts, assignments, templates, and employee-initiated swap/unavailability
requests. Response shapes are assembled as plain dicts in the route layer
(see routes/employee_schedule/_shared.py:serialize_shift).
"""

from datetime import date, datetime, time
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ShiftStatus = Literal["draft", "published", "cancelled"]
AssignmentStatus = Literal["assigned", "confirmed", "declined"]
RequestType = Literal["swap", "drop", "unavailable"]
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
    # Employees to assign up front (optional).
    employee_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_window(self) -> "ShiftCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
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


class AssignmentCreate(BaseModel):
    employee_id: UUID


class PublishRange(BaseModel):
    """Bulk-publish every draft shift whose start falls in [start, end)."""

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _check_window(self) -> "PublishRange":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    role: Optional[str] = Field(None, max_length=150)
    department: Optional[str] = Field(None, max_length=100)
    location_id: Optional[UUID] = None
    start_time: time
    end_time: time
    break_minutes: int = Field(0, ge=0, le=1440)
    required_staff: int = Field(1, ge=1, le=99)
    days_of_week: list[Weekday] = Field(default_factory=list)
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    role: Optional[str] = Field(None, max_length=150)
    department: Optional[str] = Field(None, max_length=100)
    location_id: Optional[UUID] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: Optional[int] = Field(None, ge=0, le=1440)
    required_staff: Optional[int] = Field(None, ge=1, le=99)
    days_of_week: Optional[list[Weekday]] = None
    color: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)


class GenerateFromTemplate(BaseModel):
    """Materialize concrete shifts from a template across a date range.

    Every date in [start_date, end_date] whose weekday is in the template's
    days_of_week gets one draft shift. Overnight templates (end_time <=
    start_time) roll ends_at to the next calendar day.
    """

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _check_range(self) -> "GenerateFromTemplate":
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
        if self.request_type in ("swap", "drop") and self.shift_id is None:
            raise ValueError("shift_id is required for swap/drop requests")
        if self.request_type == "unavailable":
            if self.unavailable_start is None or self.unavailable_end is None:
                raise ValueError("unavailable_start and unavailable_end are required")
            if self.unavailable_end < self.unavailable_start:
                raise ValueError("unavailable_end must be on or after unavailable_start")
        return self


class RequestReview(BaseModel):
    decision: RequestDecision
    review_notes: Optional[str] = Field(None, max_length=2000)
