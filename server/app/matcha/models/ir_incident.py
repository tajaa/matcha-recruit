"""Pydantic models for IR (Incident Report) module."""

from datetime import datetime
from typing import Optional, Literal, Any
from uuid import UUID
from pydantic import BaseModel, Field


# Type aliases
IRIncidentType = Literal["safety", "behavioral", "property", "near_miss", "other"]
IRSeverity = Literal["critical", "high", "medium", "low"]
IRStatus = Literal["reported", "investigating", "action_required", "resolved", "closed"]
IRDocumentType = Literal["photo", "form", "statement", "other"]
IRAnalysisType = Literal["categorization", "severity", "root_cause", "recommendations", "similar"]


# ===========================================
# Witness Models
# ===========================================

class Witness(BaseModel):
    """A witness to an incident."""
    name: str
    contact: Optional[str] = None
    statement: Optional[str] = None


# ===========================================
# Category-Specific Data Models
# ===========================================

class SafetyData(BaseModel):
    """Safety/injury incident specific data."""
    injured_person: Optional[str] = None
    injured_person_role: Optional[str] = None
    body_parts: list[str] = []
    injury_type: Optional[str] = None  # cut, burn, strain, fracture, etc.
    treatment: Optional[str] = None  # first_aid, medical, er, hospitalization
    lost_days: Optional[int] = None
    equipment_involved: Optional[str] = None
    osha_recordable: Optional[bool] = None


class BehavioralData(BaseModel):
    """Behavioral/HR incident specific data."""
    parties_involved: list[dict] = []  # [{name, role}]
    policy_violated: Optional[str] = None
    prior_incidents: list[str] = []  # UUIDs of related incidents
    manager_notified: Optional[bool] = None


class PropertyData(BaseModel):
    """Property damage incident specific data."""
    asset_damaged: Optional[str] = None
    estimated_cost: Optional[float] = None
    insurance_claim: Optional[bool] = None


class NearMissData(BaseModel):
    """Near miss incident specific data."""
    potential_outcome: Optional[str] = None
    hazard_identified: Optional[str] = None
    immediate_action: Optional[str] = None
    preventive_measures: Optional[str] = None


# ===========================================
# Incident Models
# ===========================================

class IRIncidentCreate(BaseModel):
    """Request model for creating a new incident report."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    incident_type: IRIncidentType
    severity: IRSeverity = "medium"
    occurred_at: datetime
    location: Optional[str] = Field(None, max_length=255)
    reported_by_name: str = Field(..., min_length=1, max_length=255)
    reported_by_email: Optional[str] = None
    witnesses: list[Witness] = []
    category_data: Optional[dict[str, Any]] = None


class IRIncidentUpdate(BaseModel):
    """Request model for updating an incident report."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    incident_type: Optional[IRIncidentType] = None
    severity: Optional[IRSeverity] = None
    status: Optional[IRStatus] = None
    occurred_at: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=255)
    assigned_to: Optional[UUID] = None
    witnesses: Optional[list[Witness]] = None
    category_data: Optional[dict[str, Any]] = None
    root_cause: Optional[str] = None
    corrective_actions: Optional[str] = None


class IRIncidentResponse(BaseModel):
    """Response model for an incident report."""
    id: UUID
    incident_number: str
    title: str
    description: Optional[str] = None
    incident_type: IRIncidentType
    severity: IRSeverity
    status: IRStatus
    occurred_at: datetime
    location: Optional[str] = None
    reported_by_name: str
    reported_by_email: Optional[str] = None
    reported_at: datetime
    assigned_to: Optional[UUID] = None
    witnesses: list[Witness] = []
    category_data: dict[str, Any] = {}
    root_cause: Optional[str] = None
    corrective_actions: Optional[str] = None
    document_count: int = 0
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None


class IRIncidentListResponse(BaseModel):
    """Response model for listing incidents."""
    incidents: list[IRIncidentResponse]
    total: int


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
    created_at: datetime


class IRDocumentUploadResponse(BaseModel):
    """Response after uploading a document."""
    document: IRDocumentResponse
    message: str = "Document uploaded successfully"


# ===========================================
# AI Analysis Models
# ===========================================

class CategorizationAnalysis(BaseModel):
    """AI categorization analysis result."""
    suggested_type: IRIncidentType
    confidence: float
    reasoning: str
    generated_at: datetime


class SeverityAnalysis(BaseModel):
    """AI severity assessment result."""
    suggested_severity: IRSeverity
    factors: list[str]
    reasoning: str
    generated_at: datetime


class RootCauseAnalysis(BaseModel):
    """AI root cause analysis result."""
    primary_cause: str
    contributing_factors: list[str]
    prevention_suggestions: list[str]
    reasoning: str
    generated_at: datetime


class RecommendationItem(BaseModel):
    """A single corrective action recommendation."""
    action: str
    priority: Literal["immediate", "short_term", "long_term"]
    responsible_party: Optional[str] = None
    estimated_effort: Optional[str] = None


class RecommendationsAnalysis(BaseModel):
    """AI corrective action recommendations."""
    recommendations: list[RecommendationItem]
    summary: str
    generated_at: datetime


class SimilarIncident(BaseModel):
    """A similar past incident."""
    incident_id: UUID
    incident_number: str
    title: str
    incident_type: IRIncidentType
    similarity_score: float
    common_factors: list[str]


class SimilarIncidentsAnalysis(BaseModel):
    """AI similar incidents detection result."""
    similar_incidents: list[SimilarIncident]
    pattern_summary: Optional[str] = None
    generated_at: datetime


# ===========================================
# Analytics Models
# ===========================================

class AnalyticsSummary(BaseModel):
    """Summary analytics for dashboard."""
    total_incidents: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_severity: dict[str, int]
    recent_count: int  # last 30 days
    avg_resolution_days: Optional[float] = None


class TrendDataPoint(BaseModel):
    """A single point in trend data."""
    date: str
    count: int
    by_type: Optional[dict[str, int]] = None


class TrendsAnalysis(BaseModel):
    """Time-series trend data."""
    data: list[TrendDataPoint]
    period: str  # "daily", "weekly", "monthly"
    start_date: str
    end_date: str


class LocationHotspot(BaseModel):
    """A location with incident count."""
    location: str
    count: int
    by_type: dict[str, int]
    avg_severity_score: float


class LocationAnalysis(BaseModel):
    """Location-based incident analysis."""
    hotspots: list[LocationHotspot]
    total_locations: int


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
