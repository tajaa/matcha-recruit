"""Pydantic models for IR (Incident Report) module."""

from datetime import datetime, date
from typing import Optional, Literal, Any, Union
from uuid import UUID
from pydantic import BaseModel, Field


# Type aliases
IRIncidentType = Literal["safety", "behavioral", "property", "near_miss", "other"]
IRSeverity = Literal["critical", "high", "medium", "low"]
IRStatus = Literal["reported", "investigating", "action_required", "resolved", "closed"]
IRDocumentType = Literal["photo", "form", "statement", "other"]
IRAnalysisType = Literal["categorization", "severity", "root_cause", "recommendations", "similar", "consistency", "company_consistency", "policy_mapping"]


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
    """Request model for creating a new incident report.

    The slim submit form only collects: reporter name, free-text date,
    location, description, witnesses, and recommended next steps. Title,
    incident_type, and severity are inferred server-side (defaulted at
    insert; auto-classified by IRAnalyzer in a background task).
    """
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    incident_type: Optional[IRIncidentType] = None
    severity: Optional[IRSeverity] = "medium"
    # Free text accepted from the submit form ("yesterday at 3pm"); the
    # route handler parses with dateutil.parser and falls back to NOW().
    occurred_at: Union[datetime, str]
    location: Optional[str] = Field(None, max_length=255)
    reported_by_name: str = Field(..., min_length=1, max_length=255)
    reported_by_email: Optional[str] = None
    witnesses: list[Witness] = []
    category_data: Optional[dict[str, Any]] = None
    # User-entered "Recommended next steps" lands in the corrective_actions
    # column so it shows up in the existing IR detail view immediately.
    corrective_actions: Optional[str] = None
    # Accepts either employee UUIDs or HR-internal UIDs (badge / employee
    # numbers). UIDs get resolved server-side via employees.external_uid
    # before persisting; the column itself stores UUIDs only.
    involved_employee_ids: list[str] = []
    company_id: Optional[UUID] = None
    location_id: Optional[UUID] = None


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
    involved_employee_ids: Optional[list[str]] = None
    company_id: Optional[UUID] = None
    location_id: Optional[UUID] = None


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
    involved_employee_ids: list[UUID] = []
    er_case_id: Optional[UUID] = None
    document_count: int = 0
    company_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    # Denormalized context fields for display
    company_name: Optional[str] = None
    location_name: Optional[str] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
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
    from_cache: bool = False
    cache_reason: Optional[str] = None


class SeverityAnalysis(BaseModel):
    """AI severity assessment result."""
    suggested_severity: IRSeverity
    factors: list[str]
    reasoning: str
    generated_at: datetime
    from_cache: bool = False
    cache_reason: Optional[str] = None


class RootCauseAnalysis(BaseModel):
    """AI root cause analysis result."""
    primary_cause: str
    contributing_factors: list[str]
    prevention_suggestions: list[str]
    reasoning: str
    generated_at: datetime
    from_cache: bool = False
    cache_reason: Optional[str] = None


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
    from_cache: bool = False
    cache_reason: Optional[str] = None


class ScoreBreakdown(BaseModel):
    """Per-dimension similarity scores."""
    type_match: float = 0.0
    severity_proximity: float = 0.0
    category_overlap: float = 0.0
    location_similarity: float = 0.0
    temporal_pattern: float = 0.0
    text_similarity: float = 0.0
    root_cause_similarity: float = 0.0


class PrecedentMatch(BaseModel):
    """A matched precedent incident with scoring details."""
    incident_id: str
    incident_number: str
    title: str
    incident_type: IRIncidentType
    severity: IRSeverity = "medium"
    status: IRStatus = "reported"
    occurred_at: str
    resolved_at: Optional[str] = None
    resolution_days: Optional[int] = None
    root_cause: Optional[str] = None
    corrective_actions: Optional[str] = None
    resolution_effective: Optional[bool] = None
    similarity_score: float
    score_breakdown: ScoreBreakdown
    common_factors: list[str] = []


class PrecedentAnalysis(BaseModel):
    """Precedent analysis result with scored matches."""
    precedents: list[PrecedentMatch]
    pattern_summary: Optional[str] = None
    generated_at: str
    from_cache: bool = False
    cache_reason: Optional[str] = None


class ActionProbability(BaseModel):
    """Probability weight for a corrective action category."""
    category: str
    probability: float
    weighted_count: float


class ConsistencyGuidance(BaseModel):
    """Consistency guidance derived from similar incident outcomes."""
    sample_size: int
    effective_sample_size: float
    confidence: Literal["insufficient", "limited", "strong"]
    unprecedented: bool
    action_distribution: Optional[list[ActionProbability]] = None
    dominant_action: Optional[str] = None
    dominant_probability: Optional[float] = None
    weighted_avg_resolution_days: Optional[float] = None
    weighted_effectiveness_rate: Optional[float] = None
    consistency_insight: Optional[str] = None
    generated_at: str
    from_cache: bool = False


class ActionByType(BaseModel):
    """Action distribution grouped by incident type."""
    incident_type: str
    total: int
    actions: list[ActionProbability]


class ActionBySeverity(BaseModel):
    """Action distribution grouped by severity."""
    severity: str
    total: int
    actions: list[ActionProbability]


class PolicyViolationMatch(BaseModel):
    """A single policy matched against an incident."""
    policy_id: str
    policy_title: str
    relevance: Literal["violated", "bent", "related"]
    confidence: float  # 0.0-1.0
    reasoning: str
    relevant_excerpt: Optional[str] = None


class PolicyMappingAnalysis(BaseModel):
    """AI policy mapping analysis result."""
    matches: list[PolicyViolationMatch]
    summary: str
    no_matching_policies: bool = False
    generated_at: str
    from_cache: bool = False
    cache_reason: Optional[str] = None


class ConsistencyAnalytics(BaseModel):
    """Company-wide consistency analytics across resolved incidents."""
    total_resolved: int
    total_with_actions: int
    action_distribution: list[ActionProbability]
    by_incident_type: list[ActionByType]
    by_severity: list[ActionBySeverity]
    avg_resolution_by_action: dict[str, float]
    generated_at: str
    from_cache: bool = False


# ===========================================
# Analytics Models
# ===========================================

class AnalyticsSummary(BaseModel):
    """Summary analytics for dashboard."""
    total: int
    open: int
    investigating: int
    resolved: int
    closed: int
    critical: int
    high: int
    medium: int
    low: int
    by_type: dict[str, int]


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
# Risk Insights Models (cross-tier — works for both Cap and full Matcha)
# ===========================================

class RiskMatrixCell(BaseModel):
    """One cell in the location × incident_type risk matrix."""
    incident_type: str
    count: int
    severity_score: float       # AVG severity weighted critical=4..low=1
    baseline_rate: float        # company-wide rate of this type per location-day
    location_rate: float        # this location's rate of this type per location-day
    deviation_ratio: float      # location_rate / baseline_rate (1.0 = at baseline)
    flagged: bool               # deviation_ratio >= 2.0 AND count >= 3


class RiskMatrixRow(BaseModel):
    """One location row in the risk matrix."""
    location_id: Optional[UUID] = None  # null for the synthesized Unassigned bucket
    location_name: str
    total_incidents: int
    cells: list[RiskMatrixCell]


class RiskMatrixResponse(BaseModel):
    """SQL-driven Risk Matrix — locations × incident_type."""
    period_days: int
    generated_at: str
    company_total: int
    location_count: int
    rows: list[RiskMatrixRow]


class RiskTheme(BaseModel):
    """One Gemini-detected pattern across recent incidents."""
    label: str
    severity: str                       # 'low' | 'medium' | 'high' | 'critical'
    location_id: Optional[UUID] = None  # null if cross-location
    location_name: Optional[str] = None
    incident_count: int
    evidence_incident_ids: list[UUID]
    insight: str
    recommendation: str


class RiskInsightsResponse(BaseModel):
    """Gemini-driven AI Themes — recurring patterns in the recent corpus."""
    period_days: int
    generated_at: str
    location_id: Optional[UUID] = None  # echo of filter
    themes: list[RiskTheme]
    from_cache: bool = False


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


# ===========================================
# OSHA Models
# ===========================================

class OshaRecordabilityUpdate(BaseModel):
    """Request model for updating OSHA recordability on an incident."""
    osha_recordable: bool
    osha_classification: Optional[str] = None  # death, days_away, restricted_duty, medical_treatment, loss_of_consciousness, significant_injury
    osha_case_number: Optional[str] = None
    days_away_from_work: Optional[int] = 0
    days_restricted_duty: Optional[int] = 0
    date_of_death: Optional[date] = None


class Osha300LogEntry(BaseModel):
    """A single entry in the OSHA 300 log."""
    case_number: str
    employee_name: str
    job_title: Optional[str]
    date_of_injury: str
    location: Optional[str]
    description: Optional[str]
    classification: Optional[str]
    days_away: int
    days_restricted: int
    injury_type: Optional[str]
    incident_id: str


class Osha300ASummary(BaseModel):
    """OSHA 300A annual summary."""
    year: int
    establishment_name: Optional[str]
    total_cases: int
    total_deaths: int
    total_days_away_cases: int
    total_restricted_cases: int
    total_other_recordable: int
    total_days_away: int
    total_days_restricted: int
    total_injuries: int
    total_skin_disorders: int
    total_respiratory: int
    total_poisonings: int
    total_hearing_loss: int
    total_other_illnesses: int
    average_employees: Optional[int]
    total_hours_worked: Optional[int]
