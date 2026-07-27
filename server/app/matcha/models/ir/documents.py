"""Incident document upload/list shapes. Consumed by routes/ir_incidents/documents.py.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel

from ._types import IRDocumentType


# ===========================================
# Document Models
# ===========================================

class IRDocumentResponse(BaseModel):
    """Response model for an incident document."""
    id: UUID
    incident_id: UUID
    document_type: IRDocumentType
    filename: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_by: Optional[UUID] = None
    # 'authed' | 'magic_link' | None (legacy rows). Distinguishes an anonymous
    # magic-link attachment from an authed upload — both have uploaded_by NULL
    # on the anonymous path, so uploaded_by alone can't tell them apart.
    uploaded_via: Optional[str] = None
    created_at: datetime


class IRDocumentUploadResponse(BaseModel):
    """Response after uploading a document."""
    document: IRDocumentResponse
    message: str = "Document uploaded successfully"
