from enum import Enum
from typing import Optional
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date


class ComplianceCategory(str, Enum):
    minimum_wage = "minimum_wage"
    overtime = "overtime"
    sick_leave = "sick_leave"
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


class BusinessLocation(BaseModel):
    id: UUID
    company_id: UUID
    name: Optional[str] = None
    address: Optional[str] = None
    city: str
    state: str
    county: Optional[str] = None
    zipcode: str
    is_active: bool = True
    last_compliance_check: Optional[datetime] = None
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
    created_at: datetime
    read_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None


class LocationCreate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: str
    state: str
    county: Optional[str] = None
    zipcode: str


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    county: Optional[str] = None
    zipcode: Optional[str] = None
    is_active: Optional[bool] = None


class RequirementResponse(BaseModel):
    id: str
    category: str
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
    created_at: str
    read_at: Optional[str] = None


class ComplianceSummary(BaseModel):
    total_locations: int
    total_requirements: int
    unread_alerts: int
    critical_alerts: int
    recent_changes: list
