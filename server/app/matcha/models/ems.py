"""Request/response models for the EMS (Event Management System) router."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EmsEventOut(BaseModel):
    id: UUID
    company_id: UUID
    channel_id: Optional[UUID] = None
    channel_name: Optional[str] = None
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
    status: Literal["logged", "promoted", "dismissed"]
    incident_id: Optional[UUID] = None
    awaiting_reply: bool = False
    clarification_rounds: int = 0
    created_at: datetime
    updated_at: datetime


class EmsEventListResponse(BaseModel):
    events: list[EmsEventOut]
    total: int


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
