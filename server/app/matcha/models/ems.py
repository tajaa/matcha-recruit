"""Request/response models for the EMS (Event Management System) router."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class EmsEventOut(BaseModel):
    id: UUID
    company_id: UUID
    channel_id: Optional[UUID] = None
    channel_name: Optional[str] = None
    location_id: Optional[UUID] = None
    location_name: Optional[str] = None
    message_id: Optional[UUID] = None
    reporter_user_id: Optional[UUID] = None
    reporter_name: Optional[str] = None
    title: Optional[str] = None
    category: str
    severity_hint: Optional[str] = None
    doc: dict[str, Any] = Field(default_factory=dict)
    narrative: str
    incident_recommendation: bool
    incident_reasoning: Optional[str] = None
    suggested_incident_type: Optional[str] = None
    suggested_severity: Optional[str] = None
    urgency: Optional[Literal["osha", "severe"]] = None
    protocol_qualifies: Optional[bool] = None
    protocol_reasoning: Optional[str] = None
    status: Literal["logged", "completed", "promoted", "dismissed"]
    resolved_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    resolution_code: Optional[str] = None
    duplicate_of_event_id: Optional[UUID] = None
    incident_id: Optional[UUID] = None
    awaiting_reply: bool = False
    clarification_rounds: int = 0
    created_at: datetime
    updated_at: datetime


class EmsEventListResponse(BaseModel):
    events: list[EmsEventOut]
    total: int


class EmsEventDraftOut(BaseModel):
    id: UUID
    company_id: UUID
    channel_id: UUID
    source_message_id: UUID
    confirmation_message_id: Optional[UUID] = None
    reporter_user_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    narrative: str
    classified: dict[str, Any] = Field(default_factory=dict)
    urgency: Optional[Literal["osha", "severe"]] = None
    status: Literal["pending", "confirmed", "rejected", "expired"]
    event_id: Optional[UUID] = None
    decided_by: Optional[UUID] = None
    decided_at: Optional[datetime] = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class EmsEventDraftRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class EmsEventResolveRequest(BaseModel):
    resolution: Literal["completed", "no_action"]
    note: Optional[str] = Field(default=None, max_length=2000)
    resolution_code: Optional[Literal["handled", "not_event", "duplicate", "informational"]] = None
    duplicate_of_event_id: Optional[UUID] = None


class EmsEventAssignmentCreateRequest(BaseModel):
    channel_id: UUID
    assignee_user_id: UUID
    shared_title: str = Field(..., min_length=1, max_length=300)
    instructions: Optional[str] = Field(default=None, max_length=4000)
    due_at: Optional[datetime] = None
    client_request_id: Optional[UUID] = None

    @field_validator("shared_title")
    @classmethod
    def reject_blank_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Assignment title is required")
        return value

    @field_validator("instructions")
    @classmethod
    def normalize_instructions(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class EmsEventAssignmentOut(BaseModel):
    id: UUID
    company_id: UUID
    event_id: UUID
    channel_id: UUID
    channel_name: Optional[str] = None
    message_id: Optional[UUID] = None
    assignee_user_id: UUID
    assignee_name: str
    assignee_email: Optional[str] = None
    assigned_by: UUID
    shared_title: str
    instructions: Optional[str] = None
    due_at: Optional[datetime] = None
    status: Literal["assigned", "completed", "cancelled"]
    event_status: Literal["logged", "completed", "promoted", "dismissed"]
    completed_by: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    can_complete: bool = False
    can_cancel: bool = False
    can_view_event: bool = False


class EmsEventAssignmentListResponse(BaseModel):
    assignments: list[EmsEventAssignmentOut]


class EmsEventUpdate(BaseModel):
    """True PATCH via model_fields_set — an unsent field is left untouched."""
    title: Optional[str] = None
    category: Optional[str] = None
    doc: Optional[dict[str, Any]] = None
    dismissed: Optional[bool] = None


class PromoteRequest(BaseModel):
    title: Optional[str] = None
    incident_type: Optional[Literal["safety", "behavioral", "property", "near_miss", "other"]] = None
    severity: Optional[Literal["critical", "high", "medium", "low"]] = None
    occurred_at: Optional[datetime] = None
    location: Optional[str] = None
    witnesses: Optional[list[str]] = None


class PromoteResponse(BaseModel):
    incident_id: UUID


class EmsProtocolOut(BaseModel):
    notify_emails: list[str] = Field(default_factory=list)
    notify_all_admins: bool = True
    incident_definition: str = ""
    culture_notes: str = ""
    corrective_actions: str = ""
    updated_at: Optional[datetime] = None


class EmsProtocolUpdate(BaseModel):
    notify_emails: list[str] = Field(default_factory=list, max_length=20)
    notify_all_admins: bool = True
    incident_definition: str = Field("", max_length=20000)
    culture_notes: str = Field("", max_length=20000)
    corrective_actions: str = Field("", max_length=20000)
