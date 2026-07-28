"""AI analysis result shapes (categorization, severity, root cause,
recommendations, precedent, consistency, policy/statute mapping). Consumed by
routes/ir_incidents/ai_analysis.py.
"""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field

from .types import IRIncidentType, IRSeverity, IRStatus



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
    # The recommendations prompt has always asked Gemini for these two — they
    # were parsed and silently dropped before this field existed. Additive
    # with defaults so legacy cached ir_incident_analysis rows (generated
    # before this field existed) still parse.
    training_recommended: bool = False
    training_topics: list[str] = Field(default_factory=list)


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


class StatuteMatch(BaseModel):
    """A safety statute the incident implicates, from the jurisdiction catalog.

    Additive to policy mapping; the codified corpus is thin, so `statute_citation`
    is optional and `state` carries whatever jurisdiction label the catalog row
    resolved to. Rendered as an "Implicated statutes" subsection, hidden when the
    list is empty."""
    requirement_id: str
    state: str = ""
    category: str = ""
    title: str = "Requirement"
    statute_citation: Optional[str] = None
    source_url: Optional[str] = None
    relevance_reason: str = ""


class PolicyMappingAnalysis(BaseModel):
    """AI policy mapping analysis result."""
    matches: list[PolicyViolationMatch]
    summary: str
    no_matching_policies: bool = False
    generated_at: str
    from_cache: bool = False
    cache_reason: Optional[str] = None
    # Jurisdiction-statute grounding (default empty → legacy cached rows, which
    # lack these keys, parse cleanly and render no statute section).
    statute_matches: list[StatuteMatch] = []
    statute_summary: Optional[str] = None
    statute_states: list[str] = []


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
