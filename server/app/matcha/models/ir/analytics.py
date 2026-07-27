"""Dashboard analytics: summary, trends, location hotspots, the risk matrix,
risk themes, and WC scorecards. Consumed by routes/ir_incidents/analytics.py.
"""
from datetime import date
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel


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
    by_severity: Optional[dict[str, int]] = None
    recordable_count: Optional[int] = None


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


class WcLocationScorecard(BaseModel):
    """One establishment's Workers-Comp metric block for the per-site scorecard."""
    location_id: Optional[UUID] = None
    location_name: str
    city: Optional[str] = None
    state: Optional[str] = None
    metrics: dict[str, Any]


class WcByLocationResponse(BaseModel):
    """Side-by-side per-location TRIR/DART scorecards + the company roll-up.

    compute_wc_metrics is company-wide only by default; this fans it out per
    business_location (scoped incidents + location headcount) so a multi-site
    buyer sees which site drives the number.
    """
    period_days: int
    company: dict[str, Any]
    locations: list[WcLocationScorecard]
    generated_at: str


class LeadingIndicators(BaseModel):
    """Leading (predictive) safety signals — the counterpart to lagging TRIR/DART.

    Near-miss volume and the near-miss-to-recordable ratio are recognized
    leading indicators (a healthy program surfaces many near-misses per
    recordable); CAPA close-rate + time-to-close measure follow-through.
    """
    period_days: int
    near_miss_count: int
    recordable_count: int
    near_miss_to_recordable_ratio: Optional[float] = None
    near_miss_prior_count: int = 0
    near_miss_delta_pct: Optional[float] = None
    total_incident_count: int = 0
    corrective_actions_open: int = 0
    corrective_actions_overdue: int = 0
    corrective_actions_completed: int = 0
    capa_close_rate: Optional[float] = None
    avg_days_to_close: Optional[float] = None
    generated_at: str
