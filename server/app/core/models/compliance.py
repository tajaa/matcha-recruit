from enum import Enum
from typing import Optional, List, Any
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date


class ComplianceCategory(str, Enum):
    minimum_wage = "minimum_wage"
    overtime = "overtime"
    sick_leave = "sick_leave"
    meal_breaks = "meal_breaks"
    pay_frequency = "pay_frequency"
    final_pay = "final_pay"
    minor_work_permit = "minor_work_permit"
    scheduling_reporting = "scheduling_reporting"
    workers_comp = "workers_comp"
    business_license = "business_license"
    tax_rate = "tax_rate"
    posting_requirements = "posting_requirements"


class JurisdictionLevel(str, Enum):
    federal = "federal"
    state = "state"
    county = "county"
    city = "city"


class AlertSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertStatus(str, Enum):
    unread = "unread"
    read = "read"
    dismissed = "dismissed"
    actioned = "actioned"


class AlertType(str, Enum):
    change = "change"
    new_requirement = "new_requirement"
    upcoming_legislation = "upcoming_legislation"
    deadline_approaching = "deadline_approaching"


class LegislationStatus(str, Enum):
    proposed = "proposed"
    passed = "passed"
    signed = "signed"
    effective_soon = "effective_soon"
    effective = "effective"
    dismissed = "dismissed"


class BusinessLocation(BaseModel):
    id: UUID
    company_id: UUID
    jurisdiction_id: Optional[UUID] = None
    name: Optional[str] = None
    address: Optional[str] = None
    city: str
    state: str
    county: Optional[str] = None
    zipcode: str
    is_active: bool = True
    auto_check_enabled: bool = True
    auto_check_interval_days: int = 7
    next_auto_check: Optional[datetime] = None
    last_compliance_check: Optional[datetime] = None
    has_local_ordinance: Optional[bool] = None
    created_at: datetime
    updated_at: datetime


class ComplianceRequirement(BaseModel):
    id: UUID
    location_id: UUID
    category: str
    jurisdiction_level: str
    jurisdiction_name: str
    title: str
    description: Optional[str] = None
    current_value: Optional[str] = None
    numeric_value: Optional[float] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    previous_value: Optional[str] = None
    last_changed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ComplianceAlert(BaseModel):
    id: UUID
    location_id: UUID
    company_id: UUID
    requirement_id: Optional[UUID] = None
    title: str
    message: str
    severity: str
    status: str
    category: Optional[str] = None
    action_required: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    deadline: Optional[date] = None
    confidence_score: Optional[float] = None
    verification_sources: Optional[list] = None
    alert_type: Optional[str] = "change"
    effective_date: Optional[date] = None
    metadata: Optional[dict] = None
    created_at: datetime
    read_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None


class LocationCreate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: str
    state: str
    county: Optional[str] = None
    zipcode: Optional[str] = None


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    county: Optional[str] = None
    zipcode: Optional[str] = None
    is_active: Optional[bool] = None


class AutoCheckSettings(BaseModel):
    auto_check_enabled: Optional[bool] = None
    auto_check_interval_days: Optional[int] = None


class RequirementResponse(BaseModel):
    id: str
    category: str
    rate_type: Optional[str] = None
    jurisdiction_level: str
    jurisdiction_name: str
    title: str
    description: Optional[str] = None
    current_value: Optional[str] = None
    numeric_value: Optional[float] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    effective_date: Optional[str] = None
    previous_value: Optional[str] = None
    last_changed_at: Optional[str] = None


class AlertResponse(BaseModel):
    id: str
    location_id: str
    requirement_id: Optional[str] = None
    title: str
    message: str
    severity: str
    status: str
    category: Optional[str] = None
    action_required: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    deadline: Optional[str] = None
    confidence_score: Optional[float] = None
    verification_sources: Optional[list] = None
    alert_type: Optional[str] = None
    effective_date: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: str
    read_at: Optional[str] = None


class CheckLogEntry(BaseModel):
    id: str
    location_id: str
    company_id: str
    check_type: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    new_count: int = 0
    updated_count: int = 0
    alert_count: int = 0
    error_message: Optional[str] = None


class UpcomingLegislationResponse(BaseModel):
    id: str
    location_id: str
    category: Optional[str] = None
    title: str
    description: Optional[str] = None
    current_status: str
    expected_effective_date: Optional[str] = None
    impact_summary: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    confidence: Optional[float] = None
    days_until_effective: Optional[int] = None
    created_at: str


class VerificationResult(BaseModel):
    confirmed: bool
    confidence: float
    sources: List[dict] = []
    explanation: str = ""


class ComplianceSummary(BaseModel):
    total_locations: int
    total_requirements: int
    unread_alerts: int
    critical_alerts: int
    recent_changes: list
    auto_check_locations: int = 0
    upcoming_deadlines: list = []
