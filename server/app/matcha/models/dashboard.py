"""Dashboard request/response models (extracted from routes/dashboard.py, J7 foldout)."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class PendingIncident(BaseModel):
    id: UUID
    incident_number: str
    title: str
    severity: str


class ActivityItem(BaseModel):
    action: str
    timestamp: datetime
    type: str  # 'success' | 'warning' | 'neutral'


class IncidentSummary(BaseModel):
    total_open: int
    critical: int
    high: int
    medium: int
    low: int
    recent_7_days: int


class WageAlertSummary(BaseModel):
    hourly_violations: int
    salary_violations: int
    locations_affected: int


class ERCaseSummary(BaseModel):
    open_cases: int
    open: int = 0
    in_review: int = 0
    pending_determination: int = 0
    # Legacy fields kept for backward compat
    investigating: int = 0
    pending_action: int = 0


class StalePolicySummary(BaseModel):
    stale_count: int
    oldest_days: int


class EmployeeWageGapDetail(BaseModel):
    employee_id: UUID
    name: str
    job_title: Optional[str] = None
    soc_code: str
    soc_label: str
    work_city: Optional[str] = None
    work_state: Optional[str] = None
    pay_rate: float
    market_p50: float
    market_p25: Optional[float] = None
    market_p75: Optional[float] = None
    delta_dollars_per_hour: float
    delta_percent: float
    annual_cost_to_reach_p50: int
    annual_cost_to_reach_p25: int
    benchmark_tier: str
    benchmark_area: str
    flight_risk_tier: str


class RoleRollupItem(BaseModel):
    soc_code: str
    soc_label: str
    headcount: int
    below_market_count: int
    median_delta_percent: float
    total_annual_cost_to_lift_to_p50: int


class WageGapDetailsResponse(BaseModel):
    employees: List[EmployeeWageGapDetail]
    role_rollups: List[RoleRollupItem]


class ManagerHotspot(BaseModel):
    manager_id: str
    manager_name: str
    flagged_count: int


class FlightRiskWidgetSummary(BaseModel):
    """Composite flight-risk aggregate (§3.3, QSR_RETENTION_PLAN.md).

    Companion to WageGapSummary — same dollar-math language. Critical+high
    bucket counts are the actionable headline. `expected_loss_at_replacement`
    is upper-bound (assume every flagged person leaves) — same honest framing
    as `max_replacement_cost_exposure` in the wage-gap widget.
    """
    employees_evaluated: int
    critical_count: int
    high_count: int
    elevated_count: int
    low_count: int
    expected_loss_at_replacement: int
    top_driver: Optional[str] = None
    top_driver_count: int = 0
    early_tenure_count: int = 0
    manager_hotspots: List[ManagerHotspot] = []


class WageGapSummary(BaseModel):
    """Hourly-wage market-gap stats (§3.1, QSR_RETENTION_PLAN.md).

    Frames retention as a P&L bet: closing the comp gap costs $X/yr,
    `max_replacement_cost_exposure` is the worst-case if every below-market
    employee actually quits — an upper bound, not an expected loss.
    """
    hourly_employees_count: int
    employees_evaluated: int
    employees_below_market: int
    employees_at_or_above_market: int
    employees_unclassified: int
    median_delta_percent: Optional[float] = None
    dollars_per_hour_to_close_gap: float
    annual_cost_to_lift: int
    max_replacement_cost_exposure: int


class DashboardStats(BaseModel):
    active_policies: int
    pending_signatures: int
    total_employees: int
    compliance_rate: float
    pending_incidents: List[PendingIncident]
    recent_activity: List[ActivityItem]
    incident_summary: Optional[IncidentSummary] = None
    wage_alerts: Optional[WageAlertSummary] = None
    wage_gap_summary: Optional[WageGapSummary] = None
    flight_risk_summary: Optional[FlightRiskWidgetSummary] = None
    # New HR-admin focused fields
    critical_compliance_alerts: int = 0
    warning_compliance_alerts: int = 0
    er_case_summary: Optional[ERCaseSummary] = None
    stale_policies: Optional[StalePolicySummary] = None
    escalated_queries_open: int = 0
    escalated_queries_high: int = 0


class DashboardFlag(BaseModel):
    priority: int
    category: str
    location_subject: str
    description: str
    recommendation: str
    severity: str  # critical, high, medium, low
    source_type: str  # pattern, compliance, incident, er_case, wage, policy
    source_id: Optional[str] = None
    link: Optional[str] = None


class HeatMapCell(BaseModel):
    location: str
    category: str
    count: int
    worst_severity: str
    group: str = "Locations"  # Locations, Departments, Company-wide


class BusinessLocationSummary(BaseModel):
    id: str
    name: str
    city: str
    state: str


class DashboardFlagsResponse(BaseModel):
    total_flags: int
    critical_count: int
    flags: list[DashboardFlag]
    heat_map: list[HeatMapCell] = []
    locations: list[BusinessLocationSummary] = []
    analyzed_at: Optional[datetime] = None


class ClientNotification(BaseModel):
    id: str
    type: str  # "incident", "employee", "offer_letter", "er_case", "handbook", "compliance_alert"
    title: str
    subtitle: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    created_at: datetime
    link: Optional[str] = None


class ClientNotificationsResponse(BaseModel):
    items: list[ClientNotification]
    total: int


class CredentialExpiration(BaseModel):
    employee_id: str
    employee_name: str
    job_title: Optional[str] = None
    credential_type: str
    credential_label: str
    expiry_date: date
    severity: Literal["expired", "critical", "warning"]


class CredentialExpirationSummary(BaseModel):
    expired: int
    critical: int
    warning: int


class CredentialExpirationsResponse(BaseModel):
    summary: CredentialExpirationSummary
    expirations: list[CredentialExpiration]


class UpcomingItem(BaseModel):
    category: str  # compliance, credential, training, cobra, policy, ir, er, i9, separation, onboarding
    title: str
    subtitle: Optional[str] = None
    date: date
    days_until: int
    severity: str  # critical, warning, info
    link: str


class UpcomingResponse(BaseModel):
    items: list[UpcomingItem]
    total: int


class EscalatedQueryItem(BaseModel):
    id: str
    status: str
    severity: str
    title: str
    user_query: str
    ai_reply: Optional[str] = None
    ai_mode: Optional[str] = None
    ai_confidence: Optional[float] = None
    missing_fields: Optional[list] = None
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    thread_id: str
    linked_record_type: Optional[str] = None
    linked_record_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EscalatedQueryListResponse(BaseModel):
    items: list[EscalatedQueryItem]
    total: int


class ResolveBody(BaseModel):
    resolution_note: str


class DismissBody(BaseModel):
    reason: Optional[str] = None


class StatusBody(BaseModel):
    status: Literal["in_review"]
