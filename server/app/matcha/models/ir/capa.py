"""Structured corrective actions (CAPA). Consumed by routes/ir_incidents/capa.py.
"""
from datetime import datetime, date
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from .types import (
    CorrectiveActionEffectiveness,
    CorrectiveActionPriority,
    CorrectiveActionStatus,
    CorrectiveActionType,
)



class CorrectiveAction(BaseModel):
    """One structured corrective/preventive action on an incident (ir_corrective_actions).

    The accountable layer on top of the free-text ir_incidents.corrective_actions
    notes column: each row carries its own owner, due date, status lifecycle, and
    post-completion effectiveness check.
    """
    id: UUID
    incident_id: UUID
    description: str
    action_type: CorrectiveActionType = "corrective"
    priority: CorrectiveActionPriority = "short_term"
    assigned_to: Optional[UUID] = None
    # No-roster fallback owner name (mirrors ir_people), used when assigned_to is
    # unset (matcha-lite tenants may not have a managed roster).
    assignee_name: Optional[str] = None
    # Hydrated owner display name for assigned_to (populated on read).
    assigned_to_name: Optional[str] = None
    due_date: Optional[date] = None
    status: CorrectiveActionStatus = "open"
    completed_at: Optional[datetime] = None
    verified_by: Optional[UUID] = None
    verified_at: Optional[datetime] = None
    effectiveness: Optional[CorrectiveActionEffectiveness] = None
    # Set when action_type='training' and this CAPA is what assigned the
    # training (see routes/ir_incidents/capa.py + services/training_assignment.py).
    training_requirement_id: Optional[UUID] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    # Derived: due_date in the past and not yet completed/verified/cancelled.
    overdue: bool = False


class CorrectiveActionCreate(BaseModel):
    """Request model for creating a corrective action."""
    description: str = Field(..., min_length=1)
    action_type: CorrectiveActionType = "corrective"
    priority: CorrectiveActionPriority = "short_term"
    assigned_to: Optional[UUID] = None
    assignee_name: Optional[str] = None
    due_date: Optional[date] = None
    training_requirement_id: Optional[UUID] = None


class CorrectiveActionUpdate(BaseModel):
    """Request model for updating a corrective action (PATCH-style).

    Only the fields present in model_fields_set are written, so a status flip
    doesn't clobber the owner and vice-versa. completed_at / verified_* are
    stamped server-side on the corresponding status transition.
    """
    description: Optional[str] = Field(None, min_length=1)
    action_type: Optional[CorrectiveActionType] = None
    priority: Optional[CorrectiveActionPriority] = None
    assigned_to: Optional[UUID] = None
    assignee_name: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[CorrectiveActionStatus] = None
    effectiveness: Optional[CorrectiveActionEffectiveness] = None
    training_requirement_id: Optional[UUID] = None


class CorrectiveActionListResponse(BaseModel):
    """Response model for listing corrective actions."""
    actions: list[CorrectiveAction]
    total: int


class OpenCorrectiveAction(CorrectiveAction):
    """A corrective action in the company-wide open/overdue list.

    Adds incident context so the dashboard tile can link straight to the
    originating incident without a second fetch.
    """
    incident_number: str
    incident_title: str


class OpenCorrectiveActionsResponse(BaseModel):
    """Company-wide open/overdue corrective actions (dashboard + deadline worker)."""
    actions: list[OpenCorrectiveAction]
    total: int
    overdue_count: int
