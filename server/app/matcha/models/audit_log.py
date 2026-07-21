"""Shared audit-log response shapes.

``AuditLogEntry`` / ``AuditLogResponse`` were declared byte-identically in both
``er_case.py`` and ``accommodation.py``. The per-domain audit *tables* stay
separate on purpose (see the note in the root CLAUDE.md on ``log_audit``) — this
consolidates only the API response shape, which is genuinely the same contract.

Deliberately NOT folded in: ``IRAuditLogEntry`` in ``ir_incident.py``. It looks
like a third copy but carries a different field set, and IR's audit log is a
compliance artifact with its own retention story — collapsing it into this would
couple an OSHA-adjacent record to two unrelated domains' schema churn.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    """An entry in the audit log."""
    id: UUID
    case_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime


class AuditLogResponse(BaseModel):
    """Response for listing audit log entries."""
    entries: list[AuditLogEntry]
    total: int
