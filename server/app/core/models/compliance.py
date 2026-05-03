from enum import Enum
from typing import Optional, List, Any
from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime, date


class ComplianceCategory(str, Enum):
    # Labor
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
    leave = "leave"
    workplace_safety = "workplace_safety"
    anti_discrimination = "anti_discrimination"
    # Healthcare
    hipaa_privacy = "hipaa_privacy"
    billing_integrity = "billing_integrity"
    clinical_safety = "clinical_safety"
    healthcare_workforce = "healthcare_workforce"
    corporate_integrity = "corporate_integrity"
    research_consent = "research_consent"
    state_licensing = "state_licensing"
    emergency_preparedness = "emergency_preparedness"
    # Oncology
    radiation_safety = "radiation_safety"
    chemotherapy_handling = "chemotherapy_handling"
    tumor_registry = "tumor_registry"
    oncology_clinical_trials = "oncology_clinical_trials"
    oncology_patient_rights = "oncology_patient_rights"
    # Medical compliance
    health_it = "health_it"
    quality_reporting = "quality_reporting"
    cybersecurity = "cybersecurity"
    environmental_safety = "environmental_safety"
    pharmacy_drugs = "pharmacy_drugs"
    payer_relations = "payer_relations"
    reproductive_behavioral = "reproductive_behavioral"
    pediatric_vulnerable = "pediatric_vulnerable"
    telehealth = "telehealth"
    medical_devices = "medical_devices"
    transplant_organ = "transplant_organ"
    antitrust = "antitrust"
    tax_exempt = "tax_exempt"
    language_access = "language_access"
    records_retention = "records_retention"
    marketing_comms = "marketing_comms"
    emerging_regulatory = "emerging_regulatory"
    # Life Sciences
    gmp_manufacturing = "gmp_manufacturing"
    glp_nonclinical = "glp_nonclinical"
    clinical_trials_gcp = "clinical_trials_gcp"
    drug_supply_chain = "drug_supply_chain"
    sunshine_open_payments = "sunshine_open_payments"
    biosafety_lab = "biosafety_lab"


class JurisdictionLevel(str, Enum):
    federal = "federal"
    state = "state"
    county = "county"
    city = "city"
    special_district = "special_district"
    regulatory_body = "regulatory_body"
    # International levels
    national = "national"       # Country-level law
    province = "province"       # Subnational division (international)
    region = "region"           # UK constituent countries, etc.


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
    state: Optional[str] = None
    county: Optional[str] = None
    zipcode: Optional[str] = None
    country_code: str = "US"
    is_active: bool = True
    auto_check_enabled: bool = True
    auto_check_interval_days: int = 7
    next_auto_check: Optional[datetime] = None
    last_compliance_check: Optional[datetime] = None
    has_local_ordinance: Optional[bool] = None
    source: Optional[str] = "manual"
    coverage_status: Optional[str] = "covered"
    employee_count: Optional[int] = 0
    facility_attributes: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("facility_attributes", mode="before")
    @classmethod
    def parse_facility_attributes(cls, v):
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v


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
    state: Optional[str] = None
    county: Optional[str] = None
    zipcode: Optional[str] = None
    country_code: str = "US"
    facility_attributes: Optional[dict] = None


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    county: Optional[str] = None
    zipcode: Optional[str] = None
    is_active: Optional[bool] = None


class FacilityAttributesUpdate(BaseModel):
    entity_type: Optional[str] = None
    payer_contracts: Optional[List[str]] = None
    bed_count: Optional[int] = None
    teaching_hospital: Optional[bool] = None


class AutoCheckSettings(BaseModel):
    auto_check_enabled: Optional[bool] = None
    auto_check_interval_days: Optional[int] = None


class RequirementResponse(BaseModel):
    id: str
    category: str
    rate_type: Optional[str] = None
    applicable_industries: Optional[List[str]] = None
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
    affected_employee_count: Optional[int] = None
    affected_employee_names: Optional[List[str]] = None
    min_wage_violation_count: Optional[int] = None
    is_pinned: bool = False


class PinRequirementRequest(BaseModel):
    is_pinned: bool = True


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
    impact_summary: Optional[str] = None
    affected_employee_count: Optional[int] = None
    created_at: str
    read_at: Optional[str] = None


class CalendarItem(BaseModel):
    """Compliance calendar row — a non-dismissed alert with a deadline,
    enriched with location context and a status bucket the UI can group by.
    """
    id: str
    location_id: str
    location_name: Optional[str] = None
    location_state: Optional[str] = None
    jurisdiction_name: Optional[str] = None
    requirement_id: Optional[str] = None
    title: str
    category: Optional[str] = None
    severity: str
    deadline: str  # ISO date — calendar items always have one
    derived_status: str  # 'overdue' | 'due_soon' | 'upcoming' | 'future'
    days_until_due: int
    action_required: Optional[str] = None
    alert_status: str  # underlying alert status (unread / read / actioned)
    created_at: str


class PayerPolicyResponse(BaseModel):
    id: str
    payer_name: str
    payer_type: Optional[str] = None
    policy_number: Optional[str] = None
    policy_title: Optional[str] = None
    procedure_codes: list[str] = []
    procedure_description: Optional[str] = None
    coverage_status: str = "conditional"
    requires_prior_auth: bool = False
    clinical_criteria: Optional[str] = None
    documentation_requirements: Optional[str] = None
    medical_necessity_criteria: Optional[str] = None
    age_restrictions: Optional[str] = None
    frequency_limits: Optional[str] = None
    source_url: Optional[str] = None
    source_document: Optional[str] = None
    effective_date: Optional[str] = None
    last_reviewed: Optional[str] = None


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
    affected_employee_count: Optional[int] = None
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


# ── Hierarchical Compliance Response Schemas ──────────────────────────────
# ALL intelligence is computed server-side. Frontend just renders these.


class TriggerActivation(BaseModel):
    """Server-evaluated trigger result — frontend just displays this."""
    trigger_type: str
    trigger_key: Optional[str] = None
    trigger_value: Optional[Any] = None
    matched: bool = True


class JurisdictionLevelRequirement(BaseModel):
    """A single requirement at one jurisdiction level. Server has already
    determined status, evaluated triggers, and resolved citations."""
    id: str
    jurisdiction_level: str
    jurisdiction_name: str
    title: str
    description: Optional[str] = None
    current_value: Optional[str] = None
    numeric_value: Optional[float] = None
    source_url: Optional[str] = None
    statute_citation: Optional[str] = None
    status: str = "active"
    canonical_key: Optional[str] = None
    triggered_by: Optional[List[TriggerActivation]] = None


class PrecedenceInfo(BaseModel):
    """Server-resolved precedence determination."""
    precedence_type: str
    reasoning_text: Optional[str] = None
    legal_citation: Optional[str] = None
    trigger_condition: Optional[dict] = None


class CategoryComplianceStack(BaseModel):
    """Fully resolved compliance stack for one category."""
    category: str
    category_label: str
    domain: Optional[str] = None
    authority_type: Optional[str] = None
    governing_level: str
    governing_requirement: JurisdictionLevelRequirement
    precedence: Optional[PrecedenceInfo] = None
    all_levels: List[JurisdictionLevelRequirement]
    affected_employee_count: Optional[int] = None


class HierarchicalComplianceResponse(BaseModel):
    """Complete server-resolved compliance view for a location.
    Every field is final — no client-side post-processing needed."""
    location_id: str
    location_name: str
    city: str
    state: str
    facility_attributes: Optional[dict] = None
    categories: List[CategoryComplianceStack]
    total_categories: int
    total_requirements: int
