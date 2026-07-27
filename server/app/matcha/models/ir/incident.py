"""Incident create/update/response plus the per-type structured payloads
(safety / behavioral / property / near-miss) and witness + involved-person
shapes. Consumed by routes/ir_incidents/crud.py.
"""
from datetime import datetime, date
from typing import Optional, Literal, Any, Union
from uuid import UUID
from pydantic import BaseModel, Field

from ._types import IRIncidentType, IRSeverity, IRStatus



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
    # OSHA Privacy Case signals (29 CFR 1904.29(b)(6)-(b)(10)). These structured
    # fields drive the deterministic name-masking on the 300/301 log — see
    # app.core.services.osha_privacy.determine_privacy_case. Populated by the IR
    # Copilot / Gemini "data organization" pass (and editable by a reviewer).
    intimate_injury: bool = False               # injury to an intimate/reproductive body part
    from_sexual_assault: bool = False           # injury resulted from a sexual assault
    infectious_agent: Optional[str] = None      # none | hiv | hepatitis | tuberculosis | other
    contaminated_sharps: bool = False           # needlestick/cut from a contaminated sharp
    # Employee's explicit opt-out ("withhold my name"); only takes effect for
    # an ILLNESS case. Human-entered (Gemini cannot infer a privacy choice).
    employee_privacy_requested: bool = False


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


class InvolvedPerson(BaseModel):
    """A person linked to an incident in a given role (ir_people).

    Distinct from involved_employee_ids (real employees roster). This is the
    matcha-lite no-roster identity surfaced on the incident detail view.
    """
    id: UUID
    display_name: str
    role: Literal["reporter", "involved", "witness", "interviewee"]


class InvolvedEmployee(BaseModel):
    """A roster employee linked to an incident via involved_employee_ids.

    Hydrated (name + role context) version of the raw UUIDs, so the detail
    view can show "Jane Doe · Nurse" instead of a truncated id. Distinct
    from InvolvedPerson, which is the name-only no-roster identity.
    """
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    employment_status: Optional[str] = None


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
    # Lightweight no-roster people linked to this incident (ir_people).
    # Populated by the single-incident GET; empty on list/create responses.
    involved_people: list[InvolvedPerson] = []
    # Hydrated roster employees (names for involved_employee_ids). Same
    # lifecycle as involved_people: populated on single GET + update, empty
    # on list/create.
    involved_employees: list[InvolvedEmployee] = []
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
    # OSHA recordability + WC claim depth (wcdeep01) — lets the incident UI
    # classify a recordable so the broker WC analytics populate.
    osha_recordable: Optional[bool] = None
    wc_claim_type: Optional[str] = None
    post_termination: Optional[bool] = None
    return_to_work_date: Optional[date] = None


class IRIncidentListResponse(BaseModel):
    """Response model for listing incidents."""
    incidents: list[IRIncidentResponse]
    total: int
