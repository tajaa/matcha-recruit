"""Pydantic models for the master-admin onboarding wizard.

Shapes the request/response payloads for the wizard's 9 endpoints under
/admin/onboarding. The wizard persists each step into onboarding_sessions
JSONB columns (`basics`, `size`, `locations`, `ai_scope`, `resolved_scope`),
so the models double as the validation gate for what's allowed inside
those JSONB blobs.
"""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr, field_validator


def _empty_to_none(v: Optional[str]) -> Optional[str]:
    """Coerce empty/whitespace strings to None.

    The wizard's <select> emits "" when the user picks the "—" option,
    and Gemini sometimes emits "" for broader-than-state scope. Pydantic
    min_length validators reject both — strip them at the boundary so
    callers can keep using `state or null` semantics.
    """
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    return v


# ── Step 1: Basics ──────────────────────────────────────────────────────

class BasicsPayload(BaseModel):
    """Industry + specialty + business name + owner email captured at Step 1.

    ``description`` is a free-text blurb the admin writes describing what the
    company actually does (lab work, grad students, late-night service, etc.).
    Gemini treats it as the most authoritative source for the scope expansion
    in Step 4 — without it the AI only sees industry+specialty enums and
    misses non-obvious compliance buckets.
    """
    business_name: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=64)
    specialty: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=2000)
    owner_email: EmailStr
    owner_name: Optional[str] = Field(default=None, max_length=200)
    entity_type: Optional[str] = Field(default=None, max_length=64)

    _coerce_empty = field_validator(
        "specialty", "description", "owner_name", "entity_type",
        mode="before",
    )(lambda cls, v: _empty_to_none(v))


# ── Step 2: Size ────────────────────────────────────────────────────────

class SizePayload(BaseModel):
    """Headcount totals — Phase 1 captures counts only, no employee rows."""
    full_time: int = Field(default=0, ge=0, le=100_000)
    part_time: int = Field(default=0, ge=0, le=100_000)
    contractor: int = Field(default=0, ge=0, le=100_000)
    unknown: int = Field(default=0, ge=0, le=100_000)
    source: Literal["csv", "hris", "manual", "skipped"] = "manual"
    hris_provider: Optional[str] = None


# ── Step 3: Locations ───────────────────────────────────────────────────

class LocationInput(BaseModel):
    """One business location. State NULL only for company-wide sentinel."""
    name: Optional[str] = Field(default=None, max_length=200)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, min_length=2, max_length=2)
    county: Optional[str] = Field(default=None, max_length=100)
    zipcode: Optional[str] = Field(default=None, max_length=10)
    facility_attributes: dict[str, Any] = Field(default_factory=dict)

    _coerce_empty = field_validator(
        "name", "address", "city", "state", "county", "zipcode",
        mode="before",
    )(lambda cls, v: _empty_to_none(v))


class LocationsPayload(BaseModel):
    locations: list[LocationInput] = Field(min_length=1, max_length=50)


# ── Step 4 / 5: AI scope + bank resolution ──────────────────────────────

class AIScopeCategory(BaseModel):
    category_slug: str
    scope: Literal["federal", "state", "county", "city"]
    reason: Optional[str] = None


class AIScopeCertification(BaseModel):
    slug: str
    name: str
    issuing_authority: Optional[str] = None
    scope_level: Literal["federal", "state", "specialty"] = "federal"
    renewal_period_months: Optional[int] = Field(default=None, ge=1, le=120)


class AIScopeLicense(BaseModel):
    slug: str
    name: str
    issuing_authority: Optional[str] = None
    scope_level: Literal["federal", "state", "specialty"] = "state"
    renewal_period_months: Optional[int] = Field(default=None, ge=1, le=120)


class AIScopeJurisdiction(BaseModel):
    state: Optional[str] = Field(default=None, min_length=2, max_length=3)
    county: Optional[str] = None
    city: Optional[str] = None

    _coerce_empty = field_validator("state", "county", "city", mode="before")(
        lambda cls, v: _empty_to_none(v)
    )


class AIScopePolicy(BaseModel):
    """A written policy the company must maintain (HIPAA privacy policy,
    bloodborne exposure control plan, etc.)."""
    slug: str
    name: str
    scope_level: Literal["federal", "state", "county", "city", "specialty"] = "federal"
    reason: Optional[str] = None


class AIScopeCredential(BaseModel):
    """An employee/professional credential, inferred from the staff
    described in the company's basics (e.g. BCBA, RBT). Distinct from
    company-level certifications/licenses."""
    slug: str
    name: str
    issuing_authority: Optional[str] = None
    applies_to_role: Optional[str] = None
    scope_level: Literal["federal", "state", "specialty"] = "specialty"
    renewal_period_months: Optional[int] = Field(default=None, ge=1, le=120)
    reason: Optional[str] = None


class AIScope(BaseModel):
    """Raw AI output BEFORE bank reconciliation."""
    naics_sector: Optional[str] = None
    compliance_categories: list[AIScopeCategory] = Field(default_factory=list)
    required_certifications: list[AIScopeCertification] = Field(default_factory=list)
    required_licenses: list[AIScopeLicense] = Field(default_factory=list)
    required_policies: list[AIScopePolicy] = Field(default_factory=list)
    required_credentials: list[AIScopeCredential] = Field(default_factory=list)
    applicable_jurisdictions: list[AIScopeJurisdiction] = Field(default_factory=list)


class ResolvedScopeExisting(BaseModel):
    """A requirement from the shared bank that the AI scope mapped to."""
    requirement_id: UUID
    category_slug: str
    canonical_key: Optional[str] = None
    title: Optional[str] = None
    scope_level: str
    location_id: Optional[UUID] = None


class ResolvedScopeMissing(BaseModel):
    """An AI-suggested requirement with no bank match — needs research dispatch."""
    category_slug: str
    scope_level: str
    state: Optional[str] = None
    county: Optional[str] = None
    city: Optional[str] = None
    reason: Optional[str] = None


class ResolvedScopeAmbiguous(BaseModel):
    """An AI jurisdiction tuple that matched >1 bank row (Springfield problem)."""
    category_slug: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    why: Optional[str] = None


class ResolvedScope(BaseModel):
    existing: list[ResolvedScopeExisting] = Field(default_factory=list)
    missing: list[ResolvedScopeMissing] = Field(default_factory=list)
    ambiguous: list[ResolvedScopeAmbiguous] = Field(default_factory=list)


# ── Session shape (wire response) ───────────────────────────────────────

OnboardingSessionStep = Literal[
    "basics", "size", "locations", "scope", "gaps", "review", "done"
]

OnboardingSessionStatus = Literal["in_progress", "finalized", "abandoned"]


class OnboardingSessionSummary(BaseModel):
    """Compact row shape for the index page."""
    id: UUID
    schema_version: int
    step: OnboardingSessionStep
    status: OnboardingSessionStatus
    business_name: Optional[str] = None
    industry: Optional[str] = None
    company_id: Optional[UUID] = None
    owner_email: Optional[str] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class OnboardingSessionDetail(BaseModel):
    """Full hydrated session — what GET /sessions/{id} returns."""
    id: UUID
    schema_version: int
    step: OnboardingSessionStep
    status: OnboardingSessionStatus
    created_by: UUID
    company_id: Optional[UUID] = None
    owner_email: Optional[str] = None
    owner_user_id: Optional[UUID] = None
    invite_token: Optional[str] = None
    idempotency_key: Optional[str] = None
    basics: dict[str, Any] = Field(default_factory=dict)
    size: dict[str, Any] = Field(default_factory=dict)
    locations: list[dict[str, Any]] = Field(default_factory=list)
    ai_scope: Optional[dict[str, Any]] = None
    resolved_scope: Optional[dict[str, Any]] = None
    gap_analysis: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


# ── Request bodies ──────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)


class PatchSessionRequest(BaseModel):
    """Partial save of step data. Only one of these is set per call.

    `step` is set when the wizard advances to a new step (server moves
    the cursor); omitted on plain saves.
    """
    step: Optional[OnboardingSessionStep] = None
    basics: Optional[BasicsPayload] = None
    size: Optional[SizePayload] = None
    locations: Optional[LocationsPayload] = None


class DispatchResearchRequest(BaseModel):
    approved_missing_ids: list[str] = Field(default_factory=list, max_length=200)


class FinalizeResponse(BaseModel):
    session_id: UUID
    company_id: UUID
    invite_token: Optional[str] = None
    scope_rows_written: int
    certifications_written: int
    licenses_written: int


class SuggestedCategory(BaseModel):
    category_slug: str
    scope: Literal["federal", "state", "county", "city"]
    reason: Optional[str] = None


class SuggestedCertification(BaseModel):
    slug: str
    name: str
    reason: Optional[str] = None


class SuggestedLicense(BaseModel):
    slug: str
    name: str
    reason: Optional[str] = None


class SuggestedJurisdiction(BaseModel):
    state: Optional[str] = None
    county: Optional[str] = None
    city: Optional[str] = None
    reason: Optional[str] = None

    _coerce_empty = field_validator("state", "county", "city", mode="before")(
        lambda cls, v: _empty_to_none(v)
    )


class GapCheckResult(BaseModel):
    """End-of-wizard safety-net suggestions from Gemini.

    Empty arrays + a confirming summary is the "all clear" response.
    """
    suggested_compliance_categories: list[SuggestedCategory] = Field(default_factory=list)
    suggested_certifications: list[SuggestedCertification] = Field(default_factory=list)
    suggested_licenses: list[SuggestedLicense] = Field(default_factory=list)
    suggested_jurisdictions: list[SuggestedJurisdiction] = Field(default_factory=list)
    summary: Optional[str] = None


class GapCheckResponse(BaseModel):
    session_id: UUID
    gap_check: GapCheckResult


class CreateCompanyResponse(BaseModel):
    session_id: UUID
    company_id: UUID
    company_wide_location_id: UUID


class ExpandScopeResponse(BaseModel):
    session_id: UUID
    ai_scope: AIScope


class ResolveScopeResponse(BaseModel):
    session_id: UUID
    resolved_scope: ResolvedScope


class DispatchResearchResponse(BaseModel):
    session_id: UUID
    dispatched: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


# ── Gap-analysis dossier ────────────────────────────────────────────────


class DossierCompany(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    specialty: Optional[str] = None
    description: Optional[str] = None
    entity_type: Optional[str] = None
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None


class DossierCounts(BaseModel):
    covered: int = 0
    gaps: int = 0
    ambiguous: int = 0
    certifications: int = 0
    licenses: int = 0
    policies: int = 0
    credentials: int = 0
    suggestions: int = 0


class DossierCoverage(BaseModel):
    # Loose dicts — coverage items vary by scope_level; the assembler is
    # the source of truth and the frontend renders defensively.
    covered: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    ambiguous: list[dict[str, Any]] = Field(default_factory=list)


class GapAnalysisDossier(BaseModel):
    """Assembled, durable onboarding gap analysis — the team's handoff doc."""
    generated_at: Optional[str] = None
    session_id: Optional[str] = None
    status: Optional[str] = None
    company: DossierCompany = Field(default_factory=DossierCompany)
    headcount: dict[str, Any] = Field(default_factory=dict)
    locations: list[dict[str, Any]] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    coverage: DossierCoverage = Field(default_factory=DossierCoverage)
    ai_suggestions: dict[str, Any] = Field(default_factory=dict)
    counts: DossierCounts = Field(default_factory=DossierCounts)
