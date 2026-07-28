"""IR audit trail shapes. Consumed by routes/ir_incidents/audit_log.py.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


# ===========================================
# Audit Log Models
# ===========================================

class IRAuditLogEntry(BaseModel):
    """An entry in the audit log."""
    id: UUID
    incident_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime


class IRAuditLogResponse(BaseModel):
    """Response for listing audit log entries."""
    entries: list[IRAuditLogEntry]
    total: int
