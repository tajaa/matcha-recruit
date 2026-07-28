"""The no-roster people index: per-person summary, role counts, and history.
Consumed by routes/ir_incidents/people.py.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel

from .types import IRIncidentType, IRPersonRole, IRSeverity, IRStatus


class IRPersonSummary(BaseModel):
    """A person in the IR people index, with their total incident count."""
    id: UUID
    display_name: str
    email: Optional[str] = None
    verified: bool = False
    incident_count: int = 0
    last_seen: Optional[datetime] = None


class IRPersonRoleCount(BaseModel):
    """How many incidents a person appears in, for one role."""
    role: IRPersonRole
    count: int


class IRPersonIncidentRef(BaseModel):
    """A single incident a person appears in (with their role on it)."""
    id: UUID
    incident_number: str
    title: str
    incident_type: IRIncidentType
    severity: IRSeverity
    status: IRStatus
    occurred_at: Optional[datetime] = None
    role: IRPersonRole


class IRPersonHistory(BaseModel):
    """Per-person, role-aware incident history."""
    person: IRPersonSummary
    role_breakdown: list[IRPersonRoleCount] = []
    incidents: list[IRPersonIncidentRef] = []
