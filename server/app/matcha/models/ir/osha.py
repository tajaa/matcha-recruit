"""OSHA 300 / 301 / 300A log shapes and the ITA electronic-filing request and
response types. Consumed by routes/ir_incidents/osha/.
"""
from datetime import datetime, date
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


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
    # WC claim depth (wcdeep01) — feeds the broker WC analytics.
    wc_claim_type: Optional[str] = None  # acute | cumulative_trauma | unknown
    post_termination: Optional[bool] = None
    return_to_work_date: Optional[date] = None


class Osha300LogEntry(BaseModel):
    """A single entry in the OSHA 300 log.

    ``employee_name`` is the literal string "Privacy Case" when the incident is
    an OSHA privacy case (real name resolvable only via the confidential
    endpoint). ``description`` is the structured clinical phrase (never the raw
    reporter narrative), so no patient/third-party name reaches the export.
    """
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
    is_privacy_case: bool = False
    privacy_case_reason: Optional[str] = None


class OshaPrivacyCaseEntry(BaseModel):
    """One row of the confidential privacy-case reference list.

    Maps the public log's anonymous case number back to the real employee name
    (29 CFR 1904.29(b)(9)). Served only by the privileged, company-scoped,
    audit-logged ``/osha/privacy-cases`` endpoint — never the public 300 log.
    """
    case_number: str
    real_employee_name: str
    privacy_case_reason: Optional[str] = None
    classification: Optional[str] = None
    date_of_injury: str
    incident_id: str


class OshaCaseDetail(BaseModel):
    """One injured employee's OSHA case on a recordable incident.

    The authoritative per-case record (``ir_osha_case_details``): each injured
    person carries their own classification, days away/restricted, M-column
    injury type, and Privacy Case answer. ``case_key`` = the employee UUID (as
    str) or ``"reporter"``; ``privacy_case_reason`` is tri-state — ``None`` = not
    yet asked, ``"none"`` = asked and cleared (not a privacy case), else the
    OSHA reason.
    """
    incident_id: str
    case_key: str
    employee_id: Optional[str] = None
    case_seq: int = 1
    classification: Optional[str] = None
    days_away: int = 0
    days_restricted: int = 0
    injury_type: Optional[str] = None
    privacy_case_reason: Optional[str] = None


class Osha300ASummary(BaseModel):
    """OSHA 300A annual summary — per establishment (business_location)."""
    year: int
    establishment_name: Optional[str]
    # Establishment identity (EIN/NAICS fall back to company-level when the
    # location row leaves them null). Needed for the 300A PDF + ITA filing.
    establishment_id: Optional[str] = None
    ein: Optional[str] = None
    naics: Optional[str] = None
    # Human-readable industry title derived from the NAICS code (subsector
    # level) — fills the 300A "Industry description" field + ITA CSV column.
    industry_description: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
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
    # Company-level "Sign here" defaults — render in the 300A PDF cert block.
    # Sourced from companies.executive_*, NOT per-establishment.
    executive_name: Optional[str] = None
    executive_title: Optional[str] = None
    executive_phone: Optional[str] = None
    # average_employees auto-computes from the active roster at the location but
    # is overridable; total_hours_worked is manual (Finch HRIS cannot supply it).
    average_employees: Optional[int]
    total_hours_worked: Optional[int]
    certified_by: Optional[str] = None
    certified_title: Optional[str] = None
    certified_date: Optional[date] = None
    # Non-blocking data-quality flags for this establishment/year: recordable
    # incidents whose classification is missing (won't foot into G/H/I/J
    # meaningfully) or that are unassigned to a location (excluded from this and
    # every 300A/ITA filing). Surfaced so a silently-wrong federal form can't
    # print without a warning.
    data_quality_warnings: list[str] = []


class ItaCredentialUpdate(BaseModel):
    """Store/replace the company's OSHA ITA API token (encrypted at rest)."""
    api_token: str = Field(..., min_length=1, max_length=4000)


class ItaCredentialStatus(BaseModel):
    """Whether an ITA API token is on file — never returns the token itself."""
    configured: bool
    updated_at: Optional[datetime] = None


class ItaSubmitRequest(BaseModel):
    """Trigger a direct ITA electronic submission for a calendar year."""
    year: int = Field(..., ge=2015, le=2100)
    attested: bool = False
    # A year that already filed successfully is refused with 409 unless the
    # caller explicitly asks to file again (an amended filing). Guards the
    # double-click / retried-POST case — this submits to OSHA for real.
    resubmit: bool = False


class ItaSubmitResponse(BaseModel):
    """Outcome of a submit attempt (no secrets)."""
    status: str  # submitted | rejected | error | not_configured
    submission_id: Optional[str] = None
    establishment_count: int = 0
    error: Optional[str] = None


class ItaSubmission(BaseModel):
    """One row of the ITA filing history."""
    id: UUID
    location_id: Optional[UUID] = None
    year: int
    status: str
    ita_submission_id: Optional[str] = None
    establishment_count: int = 0
    error_detail: Optional[str] = None
    submitted_by: Optional[UUID] = None
    submitted_at: datetime


class ItaSubmissionListResponse(BaseModel):
    submissions: list[ItaSubmission]
    total: int


class Osha300ASaveRequest(BaseModel):
    """Persist manual hours / headcount override / certification for a 300A.

    Upserts osha_annual_summaries for (company, location, year). The total_*
    counts are recomputed server-side from recordable incidents so the saved
    snapshot stays consistent — only the fields below come from the user.
    """
    location_id: UUID
    year: int
    total_hours_worked: Optional[int] = None
    average_employees: Optional[int] = None  # override of the auto roster count
    certified_by: Optional[str] = None
    certified_title: Optional[str] = None
    certified_date: Optional[date] = None
