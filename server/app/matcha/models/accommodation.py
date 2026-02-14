"""Pydantic models for ADA Accommodation Case Management."""

from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field


# Type aliases
AccommodationCaseStatus = Literal[
    "requested", "interactive_process", "medical_review",
    "approved", "denied", "implemented", "review", "closed"
]
DisabilityCategory = Literal[
    "physical", "cognitive", "sensory", "mental_health",
    "chronic_illness", "pregnancy", "other"
]
AccommodationDocType = Literal[
    "medical_certification", "accommodation_request_form",
    "interactive_process_notes", "job_description",
    "hardship_analysis", "approval_letter", "other"
]
AccommodationAnalysisType = Literal[
    "accommodation_suggestions", "hardship_assessment", "job_function_analysis"
]


# ===========================================
# Case Models
# ===========================================

class AccommodationCaseCreate(BaseModel):
    """Request model for creating a new accommodation case."""
    employee_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    disability_category: Optional[DisabilityCategory] = None
    requested_accommodation: Optional[str] = Field(None, max_length=5000)
    linked_leave_id: Optional[UUID] = None


class AccommodationCaseUpdate(BaseModel):
    """Request model for updating an accommodation case."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    status: Optional[AccommodationCaseStatus] = None
    disability_category: Optional[DisabilityCategory] = None
    requested_accommodation: Optional[str] = Field(None, max_length=5000)
    approved_accommodation: Optional[str] = Field(None, max_length=5000)
    denial_reason: Optional[str] = Field(None, max_length=5000)
    assigned_to: Optional[UUID] = None


class AccommodationCaseResponse(BaseModel):
    """Response model for an accommodation case."""
    id: UUID
    case_number: str
    org_id: UUID
    employee_id: UUID
    linked_leave_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    disability_category: Optional[str] = None
    status: AccommodationCaseStatus
    requested_accommodation: Optional[str] = None
    approved_accommodation: Optional[str] = None
    denial_reason: Optional[str] = None
    undue_hardship_analysis: Optional[str] = None
    assigned_to: Optional[UUID] = None
    created_by: Optional[UUID] = None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None


class AccommodationCaseListResponse(BaseModel):
    """Response model for listing accommodation cases."""
    cases: list[AccommodationCaseResponse]
    total: int


class AccommodationEmployeeOption(BaseModel):
    """Employee option payload used by accommodations UI forms."""
    id: UUID
    first_name: str
    last_name: str
    email: str


# ===========================================
# Document Models
# ===========================================

class AccommodationDocumentResponse(BaseModel):
    """Response model for an accommodation document."""
    id: UUID
    case_id: UUID
    document_type: str
    filename: str
    file_path: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_by: Optional[UUID] = None
    created_at: datetime


# ===========================================
# Analysis Models
# ===========================================

class AccommodationAnalysisResponse(BaseModel):
    """Response model for an accommodation analysis."""
    analysis_type: str
    analysis_data: dict
    generated_by: Optional[UUID] = None
    generated_at: datetime


# ===========================================
# Audit Log Models
# ===========================================

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
