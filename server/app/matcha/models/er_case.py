"""Pydantic models for ER Copilot (Employee Relations Investigation)."""

from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field


# Type aliases
ERCaseStatus = Literal["open", "in_review", "pending_determination", "closed"]
ERDocumentType = Literal["transcript", "policy", "email", "other"]
ERProcessingStatus = Literal["pending", "processing", "completed", "failed"]
ERAnalysisType = Literal["timeline", "discrepancies", "policy_check", "summary", "determination"]
ConfidenceLevel = Literal["high", "medium", "low"]
SeverityLevel = Literal["high", "medium", "low"]
ViolationSeverity = Literal["major", "minor"]


# ===========================================
# Case Models
# ===========================================

class ERCaseCreate(BaseModel):
    """Request model for creating a new ER case."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)


class ERCaseUpdate(BaseModel):
    """Request model for updating an ER case."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    status: Optional[ERCaseStatus] = None
    assigned_to: Optional[UUID] = None


class ERCaseResponse(BaseModel):
    """Response model for an ER case."""
    id: UUID
    case_number: str
    title: str
    description: Optional[str] = None
    status: ERCaseStatus
    company_id: Optional[UUID] = None
    created_by: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None


class ERCaseListResponse(BaseModel):
    """Response model for listing ER cases."""
    cases: list[ERCaseResponse]
    total: int


# ===========================================
# Document Models
# ===========================================

class ERDocumentResponse(BaseModel):
    """Response model for an ER case document."""
    id: UUID
    case_id: UUID
    document_type: ERDocumentType
    filename: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    pii_scrubbed: bool = False
    processing_status: ERProcessingStatus = "pending"
    processing_error: Optional[str] = None
    parsed_at: Optional[datetime] = None
    uploaded_by: Optional[UUID] = None
    created_at: datetime


class ERDocumentUploadResponse(BaseModel):
    """Response after uploading a document."""
    document: ERDocumentResponse
    task_id: Optional[str] = None
    message: str = "Document uploaded and queued for processing"


# ===========================================
# Timeline Analysis Models
# ===========================================

class TimelineEvent(BaseModel):
    """A single event in the timeline."""
    date: str
    time: Optional[str] = None
    description: str
    participants: list[str] = []
    source_document_id: str
    source_location: str
    confidence: ConfidenceLevel
    evidence_quote: str


class TimelineAnalysis(BaseModel):
    """Complete timeline analysis result."""
    events: list[TimelineEvent]
    gaps_identified: list[str] = []
    timeline_summary: str
    generated_at: datetime


# ===========================================
# Discrepancy Analysis Models
# ===========================================

class DiscrepancyStatement(BaseModel):
    """A statement from a witness involved in a discrepancy."""
    source_document_id: str
    speaker: str
    quote: str
    location: str


class Discrepancy(BaseModel):
    """A detected discrepancy between statements."""
    type: str  # contradiction, timeline_conflict, internal_inconsistency, implausible, omission
    severity: SeverityLevel
    description: str
    statement_1: DiscrepancyStatement
    statement_2: DiscrepancyStatement
    analysis: str


class CredibilityNote(BaseModel):
    """Assessment of a witness's credibility."""
    witness: str
    assessment: str
    reasoning: str


class DiscrepancyAnalysis(BaseModel):
    """Complete discrepancy analysis result."""
    discrepancies: list[Discrepancy]
    credibility_notes: list[CredibilityNote] = []
    summary: str
    generated_at: datetime


# ===========================================
# Policy Check Analysis Models
# ===========================================

class PolicyViolationEvidence(BaseModel):
    """Evidence supporting a policy violation."""
    source_document_id: str
    quote: str
    location: str
    how_it_violates: str


class PolicyViolation(BaseModel):
    """A detected policy violation."""
    policy_section: str
    policy_text: str
    severity: ViolationSeverity
    evidence: list[PolicyViolationEvidence]
    analysis: str


class PolicyCheckAnalysis(BaseModel):
    """Complete policy check analysis result."""
    violations: list[PolicyViolation]
    policies_potentially_applicable: list[str] = []
    summary: str
    generated_at: datetime


# ===========================================
# RAG Search Models
# ===========================================

class EvidenceSearchRequest(BaseModel):
    """Request for searching case evidence."""
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)


class EvidenceSearchResult(BaseModel):
    """A single search result from evidence."""
    chunk_id: str
    content: str
    speaker: Optional[str] = None
    source_file: str
    document_type: ERDocumentType
    page_number: Optional[int] = None
    line_range: Optional[str] = None
    similarity: float
    metadata: Optional[dict] = None


class EvidenceSearchResponse(BaseModel):
    """Response from evidence search."""
    results: list[EvidenceSearchResult]
    query: str
    total_chunks: int


# ===========================================
# Report Models
# ===========================================

class ReportGenerateRequest(BaseModel):
    """Request to generate a report."""
    determination: Optional[str] = None  # substantiated, unsubstantiated, inconclusive


class ReportResponse(BaseModel):
    """Response containing a generated report."""
    report_type: ERAnalysisType
    content: str
    generated_at: datetime
    source_documents: list[str] = []


# ===========================================
# Task/Processing Models
# ===========================================

class TaskStatusResponse(BaseModel):
    """Response for async task status."""
    task_id: Optional[str] = None
    status: str
    message: str


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
