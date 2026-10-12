"""Request bodies for the Espresso calendar (`routes/work/calendar.py`).

Times stay strings here: `calendar_service.event_fields` is the one validator,
shared with the assistant's tools, so the routes and the agent refuse the
same things with the same words.
"""
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CalendarEventCreate(BaseModel):
    title: str = Field(max_length=1000)
    start: str = Field(max_length=64)
    end: Optional[str] = Field(default=None, max_length=64)
    location: Optional[str] = Field(default=None, max_length=1000)
    notes: Optional[str] = Field(default=None, max_length=8000)
    # The assistant writes `assistant` itself; the app never claims it.
    source_kind: Literal["manual", "email", "journal"] = "manual"
    source_ref: Optional[str] = Field(default=None, max_length=200)
    source_label: Optional[str] = Field(default=None, max_length=1000)


class CalendarEventPatch(BaseModel):
    """Sent with `exclude_unset`: an absent field is unchanged; a null
    `location` or `notes` clears it."""

    title: Optional[str] = Field(default=None, max_length=1000)
    start: Optional[str] = Field(default=None, max_length=64)
    end: Optional[str] = Field(default=None, max_length=64)
    location: Optional[str] = Field(default=None, max_length=1000)
    notes: Optional[str] = Field(default=None, max_length=8000)


class CalendarPrefs(BaseModel):
    timezone: str = Field(max_length=64)


class EmailCalendarSuggest(BaseModel):
    email_id: str
    instructions: Optional[str] = Field(default=None, max_length=1000)
    # The app's own zone; stored as the person's timezone when it is valid.
    timezone: Optional[str] = Field(default=None, max_length=64)


class AppleCalendar(BaseModel):
    id: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=300)
    editable: bool


class AppleConnection(BaseModel):
    user_id: UUID
    connection_id: UUID
    calendars: list[AppleCalendar] = Field(min_length=1, max_length=50)
    destination: str = Field(min_length=1, max_length=300)


class AppleEvent(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    calendar_id: str = Field(min_length=1, max_length=300)
    title: str = Field(max_length=300)
    start: str = Field(max_length=64)
    end: str = Field(max_length=64)
    all_day: bool
    notes: Optional[str] = Field(default=None, max_length=4000)
    location: Optional[str] = Field(default=None, max_length=300)
    modified: str = Field(max_length=64)
    # Existing invitations stay read-only: EventKit cannot safely compose
    # invitees. Google handles invitations through the existing policy gate.
    editable: bool


class AppleSnapshot(BaseModel):
    connection_id: UUID
    start: str = Field(max_length=64)
    end: str = Field(max_length=64)
    events: list[AppleEvent] = Field(max_length=500)
    complete: bool = True


class AppleActionResult(BaseModel):
    status: Literal["done", "failed", "unknown"]
    error: Optional[str] = Field(default=None, max_length=300)
