"""Safety meetings (toolbox talks) — request/response models.

Lifecycle: recording -> review -> signed. Audio chunks upload + transcribe
while status='recording'; /finish compiles the summary into status='review';
the manager edits (PATCH, review only) and signs (typed name + timestamp),
which locks the record.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_ATTENDEES = 100
MAX_LIST_ITEMS = 50
_NAME_CHARS = 120
_ITEM_CHARS = 500


def _clean_str_list(value, *, max_items: int, max_chars: int) -> list[str]:
    """Trim/dedupe/cap a list of human-entered strings (attendees, topics)."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = " ".join(item.split())[:max_chars]
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        out.append(cleaned)
        if len(out) >= max_items:
            break
    return out


class ActionItem(BaseModel):
    description: str = Field(min_length=1, max_length=_ITEM_CHARS)
    owner: Optional[str] = Field(default=None, max_length=_NAME_CHARS)


class SafetyMeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic: Optional[str] = Field(default=None, max_length=2000)
    location_id: Optional[UUID] = None
    attendee_names: list[str] = []

    _clean_attendees = field_validator("attendee_names", mode="before")(
        lambda v: _clean_str_list(v, max_items=MAX_ATTENDEES, max_chars=_NAME_CHARS)
    )

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("title is required")
        return value


class SafetyMeetingUpdate(BaseModel):
    """Review-stage edits. All fields optional; only provided fields change.
    Accepted only while status='review' (a signed record is locked)."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    topic: Optional[str] = Field(default=None, max_length=2000)
    summary: Optional[str] = Field(default=None, max_length=50000)
    manager_notes: Optional[str] = Field(default=None, max_length=20000)
    attendee_names: Optional[list[str]] = None
    topics: Optional[list[str]] = None
    action_items: Optional[list[ActionItem]] = None

    _clean_attendees = field_validator("attendee_names", mode="before")(
        lambda v: None if v is None else _clean_str_list(v, max_items=MAX_ATTENDEES, max_chars=_NAME_CHARS)
    )
    _clean_topics = field_validator("topics", mode="before")(
        lambda v: None if v is None else _clean_str_list(v, max_items=MAX_LIST_ITEMS, max_chars=200)
    )

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("title is required")
        return value


class SafetyMeetingSign(BaseModel):
    signature_name: str = Field(min_length=1, max_length=200)
    confirm: bool

    @field_validator("signature_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("signature_name is required")
        return v


class TranscriptSegment(BaseModel):
    idx: int
    text: str


class SafetyMeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    location_id: Optional[UUID] = None
    location_name: Optional[str] = None
    title: str
    topic: Optional[str] = None
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    transcript_segments: list[TranscriptSegment] = []
    transcript: Optional[str] = None
    summary: Optional[str] = None
    topics: list[str] = []
    action_items: list[ActionItem] = []
    attendee_names: list[str] = []
    manager_notes: Optional[str] = None
    summary_model: Optional[str] = None
    created_by: Optional[UUID] = None
    signed_by: Optional[UUID] = None
    signed_at: Optional[datetime] = None
    signature_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class SafetyMeetingListItem(BaseModel):
    id: UUID
    title: str
    status: str
    location_name: Optional[str] = None
    attendee_count: int = 0
    started_at: datetime
    ended_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    signature_name: Optional[str] = None


class SafetyMeetingListResponse(BaseModel):
    meetings: list[SafetyMeetingListItem]


class LocationOption(BaseModel):
    id: UUID
    name: str
    city: Optional[str] = None
    state: Optional[str] = None


class LocationListResponse(BaseModel):
    locations: list[LocationOption]


class ChunkResult(BaseModel):
    """Returned per audio-chunk upload so the recording UI can append the
    transcript live. ``available=False`` means Gemini returned nothing usable
    for that chunk (the audio is still stored; the transcript just has a gap
    the manager can see)."""
    idx: int
    transcript: Optional[str] = None
    available: bool
