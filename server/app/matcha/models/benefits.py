"""Pydantic request/response shapes for the employee-benefits broker feature.

Two product scopes share these models:
- Scope 1 — Benefit Eligibility Alerts (new-hire enrollment gaps + terminated-
  but-still-deducted "premium leaks").
- Scope 2 — Cost Early-Warning / Renewal Risk Radar.

The detection engine reads from a source-agnostic ``benefit_roster_entries``
snapshot that is populated by either a Finch sync or a CSV upload, so these
shapes never reference a specific HRIS provider.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ExceptionType = Literal["new_hire_enrollment_gap", "termination_premium_leak"]
ExceptionStatus = Literal["open", "resolved", "dismissed"]
RosterSource = Literal["finch", "csv", "mock"]
RiskBand = Literal["stable", "elevated", "critical"]
DimensionType = Literal["company", "department", "location"]


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class ExceptionResolveRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


class RunDetectionRequest(BaseModel):
    """Manually trigger ingest + detect + risk-compute for one client (or all
    of a broker's active book when ``company_id`` is omitted)."""
    company_id: Optional[str] = None
    use_finch: bool = True
    use_csv: bool = True


# ---------------------------------------------------------------------------
# Responses (mostly informational — routes return plain dicts that match these)
# ---------------------------------------------------------------------------

class EligibilityException(BaseModel):
    id: str
    company_id: str
    company_name: str
    employee_name: str
    exception_type: ExceptionType
    reference_date: date
    days_elapsed: int
    days_remaining: Optional[int] = None
    estimated_monthly_leak: Optional[float] = None
    status: ExceptionStatus
    source: RosterSource
    last_nudge_sent_at: Optional[datetime] = None
    detected_at: datetime


class EligibilityExceptionsSummary(BaseModel):
    new_hire_count: int = 0
    termination_leak_count: int = 0
    total_open: int = 0
    estimated_monthly_leak: float = 0.0


class EligibilityExceptionsResponse(BaseModel):
    summary: EligibilityExceptionsSummary
    exceptions: list[EligibilityException]


class RenewalRadarCompany(BaseModel):
    company_id: str
    company_name: str
    industry: Optional[str] = None
    risk_band: RiskBand
    policy_month: Optional[int] = None
    turnover_pct: float
    turnover_delta_pct: float
    lost_workdays: int
    near_misses: int
    behavioral_incidents: int
    headcount: int
    top_trigger: Optional[str] = None
    computed_at: datetime


class RenewalRadarSummary(BaseModel):
    client_count: int = 0
    stable: int = 0
    elevated: int = 0
    critical: int = 0


class RenewalRadarResponse(BaseModel):
    summary: RenewalRadarSummary
    companies: list[RenewalRadarCompany]


class RenewalRiskDimension(BaseModel):
    dimension_type: DimensionType
    dimension_value: str
    risk_band: RiskBand
    turnover_pct: float
    turnover_baseline_pct: float
    turnover_delta_pct: float
    lost_workdays: int
    lost_workdays_delta_pct: float
    near_misses: int
    behavioral_incidents: int
    headcount: int
    gross_payroll: Optional[float] = None
    triggers: list[str] = Field(default_factory=list)


class RenewalRadarDetail(BaseModel):
    company_id: str
    company_name: str
    risk_band: RiskBand
    policy_month: Optional[int] = None
    recommendation: str
    dimensions: list[RenewalRiskDimension]
