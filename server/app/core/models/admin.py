"""Admin route request/response models (extracted from routes/admin.py, J5)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

__all__ = [
    "PlatformFeaturesUpdate",
    "MatchaWorkModelModeUpdate",
    "JurisdictionResearchModelModeUpdate",
    "ERSimilarityWeightsUpdate",
    "JurisdictionProcessRequest",
    "PlatformSettingsResponse",
    "TenantCodifiedOnlyUpdate",
    "SubscriptionSummary",
    "BusinessRegistrationResponse",
    "BusinessRegistrationListResponse",
    "RejectRequest",
    "UpdateBusinessRegistrationRequest",
    "CreateBusinessInviteRequest",
    "BusinessInviteResponse",
    "FeatureToggleRequest",
    "CompanyCreditsAdjustRequest",
    "SchedulerUpdateRequest",
    "BrokerCreateRequest",
    "BrokerUpdateRequest",
    "BrokerContractRequest",
    "BrokerCompanyLinkRequest",
    "BrokerBrandingRequest",
    "BrokerCompanyTransitionRequest",
    "BrokerCompanyTransitionUpdateRequest",
    "JurisdictionCreateRequest",
    "RequirementUpdate",
    "SpecializationDiscoverRequest",
    "SpecializationResearchRequest",
    "LocationScheduleUpdateRequest",
    "PosterOrderUpdateRequest",
    "IndustryProfileCreate",
    "IndustryProfileUpdate",
    "SpecialtyDiscoverRequest",
    "ProposedCategory",
    "SpecialtyConfirmRequest",
    "AdminNotification",
    "AdminNotificationsResponse",
    "PendingResearchRunRequest",
    "ResearchReviewDecision",
    "RequirementCodifyRequest",
    "StudioAssistantRequest",
    "CompanyProfileUpdate",
    "ErrorLogItem",
    "ErrorLogsResponse",
    "AdminAddRequirementRequest",
    "BetaInviteRequest",
    "IndividualInviteRequest",
    "MatchaLiteInviteRequest",
    "SuspendBody",
    "PasswordResetResponse",
    "TierChangeBody",
    "ChargeSummary",
    "RefundBody",
]


class PlatformFeaturesUpdate(BaseModel):
    visible_features: list[str]


class MatchaWorkModelModeUpdate(BaseModel):
    mode: str = Field(..., pattern="^(light|heavy)$")


class JurisdictionResearchModelModeUpdate(BaseModel):
    mode: str = Field(..., pattern="^(lite|light|heavy)$")


class ERSimilarityWeightsUpdate(BaseModel):
    weights: dict[str, float]


class JurisdictionProcessRequest(BaseModel):
    """Request model for processing a jurisdiction coverage request."""
    has_local_ordinance: bool = False
    county: Optional[str] = None
    admin_notes: Optional[str] = None


class PlatformSettingsResponse(BaseModel):
    visible_features: list[str]
    matcha_work_model_mode: str
    jurisdiction_research_model_mode: str
    er_similarity_weights: dict[str, float]
    tenant_codified_only: bool


class TenantCodifiedOnlyUpdate(BaseModel):
    enabled: bool


class SubscriptionSummary(BaseModel):
    """Lite snapshot of an mw_subscriptions row, surfaced in admin views."""
    pack_id: str
    status: str
    amount_cents: int
    stripe_subscription_id: str
    stripe_customer_id: str
    current_period_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None


class BusinessRegistrationResponse(BaseModel):
    """Response model for a business registration."""
    id: UUID
    company_name: str
    industry: Optional[str]
    healthcare_specialties: Optional[list[str]] = None
    company_size: Optional[str]
    owner_user_id: Optional[UUID] = None
    owner_email: str
    owner_name: str
    owner_phone: Optional[str]
    owner_job_title: Optional[str]
    status: str
    rejection_reason: Optional[str]
    approved_at: Optional[datetime]
    approved_by_email: Optional[str]
    created_at: datetime
    signup_source: Optional[str] = None
    is_personal: bool = False
    is_suspended: bool = False
    deleted_at: Optional[datetime] = None
    subscription: Optional[SubscriptionSummary] = None


class BusinessRegistrationListResponse(BaseModel):
    """List response for business registrations."""
    registrations: list[BusinessRegistrationResponse]
    total: int


class RejectRequest(BaseModel):
    """Request model for rejecting a business registration."""
    reason: str


class UpdateBusinessRegistrationRequest(BaseModel):
    """Request model for updating business registration details."""
    company_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_size: Optional[str] = Field(default=None, max_length=50)
    owner_email: Optional[EmailStr] = None
    owner_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    owner_phone: Optional[str] = Field(default=None, max_length=50)
    owner_job_title: Optional[str] = Field(default=None, max_length=100)


class CreateBusinessInviteRequest(BaseModel):
    note: Optional[str] = None
    expires_days: int = Field(default=7, ge=1, le=90)


class BusinessInviteResponse(BaseModel):
    id: UUID
    token: str
    invite_url: str
    status: str
    note: Optional[str]
    created_by_email: str
    used_by_company_name: Optional[str]
    expires_at: datetime
    used_at: Optional[datetime]
    created_at: datetime


class FeatureToggleRequest(BaseModel):
    """Request model for toggling a company feature."""
    feature: str
    enabled: bool


class CompanyCreditsAdjustRequest(BaseModel):
    credits: int
    description: Optional[str] = Field(default=None, max_length=500)


class SchedulerUpdateRequest(BaseModel):
    """Request model for updating scheduler settings."""
    enabled: Optional[bool] = None
    max_per_cycle: Optional[int] = None


class BrokerCreateRequest(BaseModel):
    broker_name: str = Field(..., min_length=2, max_length=255)
    owner_email: EmailStr
    owner_name: str = Field(..., min_length=2, max_length=255)
    owner_password: Optional[str] = Field(default=None, min_length=8)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=120)
    support_routing: str = Field(default="shared")
    billing_mode: str = Field(default="direct")
    invoice_owner: str = Field(default="matcha")
    terms_required_version: str = Field(default="v1", min_length=1, max_length=50)
    allocated_seats: int = Field(default=0, ge=0, le=1_000_000)
    plan: str = Field(default="standard", pattern="^(standard|pro)$")


class BrokerUpdateRequest(BaseModel):
    status: Optional[str] = None
    support_routing: Optional[str] = None
    terms_required_version: Optional[str] = Field(default=None, min_length=1, max_length=50)
    terminated_at: Optional[datetime] = None
    grace_until: Optional[datetime] = None
    post_termination_mode: Optional[str] = None
    allocated_seats: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    plan: Optional[str] = Field(default=None, pattern="^(standard|pro)$")


class BrokerContractRequest(BaseModel):
    status: str = Field(default="active")
    billing_mode: str
    invoice_owner: str
    currency: str = Field(default="USD", min_length=3, max_length=3)
    base_platform_fee: float = 0.0
    pepm_rate: float = 0.0
    minimum_monthly_commit: float = 0.0
    pricing_rules: dict = {}


class BrokerCompanyLinkRequest(BaseModel):
    status: str = Field(default="active")
    permissions: dict = Field(default_factory=dict)
    post_termination_mode: Optional[str] = None
    grace_until: Optional[datetime] = None


class BrokerBrandingRequest(BaseModel):
    branding_mode: str = Field(default="direct")
    brand_display_name: Optional[str] = Field(default=None, max_length=255)
    brand_legal_name: Optional[str] = Field(default=None, max_length=255)
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = Field(default=None, max_length=20)
    secondary_color: Optional[str] = Field(default=None, max_length=20)
    login_subdomain: Optional[str] = Field(default=None, max_length=120)
    custom_login_url: Optional[str] = None
    support_email: Optional[EmailStr] = None
    support_phone: Optional[str] = Field(default=None, max_length=50)
    support_url: Optional[str] = None
    email_from_name: Optional[str] = Field(default=None, max_length=255)
    email_from_address: Optional[EmailStr] = None
    powered_by_badge: bool = True
    hide_matcha_identity: bool = False
    mobile_branding_enabled: bool = False
    theme: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class BrokerCompanyTransitionRequest(BaseModel):
    mode: str
    status: str = Field(default="planned")
    transfer_target_broker_id: Optional[UUID] = None
    grace_until: Optional[datetime] = None
    matcha_managed_until: Optional[datetime] = None
    data_handoff_status: str = Field(default="pending")
    data_handoff_notes: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class BrokerCompanyTransitionUpdateRequest(BaseModel):
    status: Optional[str] = None
    grace_until: Optional[datetime] = None
    matcha_managed_until: Optional[datetime] = None
    data_handoff_status: Optional[str] = None
    data_handoff_notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    metadata: Optional[dict] = None


class JurisdictionCreateRequest(BaseModel):
    """Request model for creating/upserting a jurisdiction."""
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=2, max_length=2)
    county: Optional[str] = Field(None, max_length=100)
    parent_id: Optional[UUID] = None


class RequirementUpdate(BaseModel):
    """Partial update fields for a jurisdiction requirement."""
    title: Optional[str] = None
    description: Optional[str] = None
    current_value: Optional[str] = None
    effective_date: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    statute_citation: Optional[str] = None


class SpecializationDiscoverRequest(BaseModel):
    specialization: str
    parent_industry: str = "healthcare"


class SpecializationResearchRequest(BaseModel):
    specialization: str
    parent_industry: str = "healthcare"
    industry_tag: str
    categories: List[str]
    states: List[str]
    cities: List[dict] = []
    industry_context: str


class LocationScheduleUpdateRequest(BaseModel):
    """Request model for updating a location's auto-check schedule."""
    auto_check_enabled: Optional[bool] = None
    auto_check_interval_days: Optional[int] = None
    next_auto_check_minutes: Optional[int] = None  # override next_auto_check to N minutes from now


class PosterOrderUpdateRequest(BaseModel):
    status: Optional[str] = None
    admin_notes: Optional[str] = None
    quote_amount: Optional[float] = None
    tracking_number: Optional[str] = None


class IndustryProfileCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    focused_categories: list[str]
    rate_types: Optional[list[str]] = None
    category_order: list[str]
    category_evidence: Optional[dict] = None


class IndustryProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    focused_categories: Optional[list[str]] = None
    rate_types: Optional[list[str]] = None
    category_order: Optional[list[str]] = None
    category_evidence: Optional[dict] = None


class SpecialtyDiscoverRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)


class ProposedCategory(BaseModel):
    # The key becomes `compliance_categories.slug` verbatim, so it must already
    # be slug-shaped: Gemini is prompted for snake_case, but the payload is
    # client-supplied and an uppercase or spaced key would create a category that
    # downstream slug comparisons never match.
    key: str = Field(..., min_length=2, max_length=60, pattern=r"^[a-z0-9][a-z0-9_]*$")
    label: Optional[str] = None
    description: Optional[str] = None
    authority_sources: List[str] = Field(default_factory=list)


class SpecialtyConfirmRequest(BaseModel):
    slug: Optional[str] = None
    label: str
    research_context: Optional[str] = None
    categories: List[ProposedCategory] = Field(default_factory=list)


class AdminNotification(BaseModel):
    id: str
    type: str  # "incident", "employee", "offer_letter", "er_case", "handbook", "compliance_alert", "registration"
    title: str
    subtitle: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    created_at: datetime
    link: Optional[str] = None


class AdminNotificationsResponse(BaseModel):
    items: list[AdminNotification]
    total: int


class PendingResearchRunRequest(BaseModel):
    item_type: str  # 'category' | 'vertical'
    request_id: Optional[str] = None          # jurisdiction_coverage_requests.id (category)
    city: Optional[str] = None
    state: Optional[str] = None
    county: Optional[str] = None
    company_id: Optional[str] = None          # (vertical)
    categories: Optional[List[str]] = None    # None = all outstanding


class ResearchReviewDecision(BaseModel):
    ids: List[str]
    request_ids: Optional[List[str]] = None
    company_ids: Optional[List[str]] = None


class RequirementCodifyRequest(BaseModel):
    citation: str
    heading: Optional[str] = None
    source_url: Optional[str] = None


class StudioAssistantRequest(BaseModel):
    question: str
    worklist: Optional[Dict[str, Any]] = None


class CompanyProfileUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    healthcare_specialties: Optional[list[str]] = None
    size: Optional[str] = None
    headquarters_state: Optional[str] = None
    headquarters_city: Optional[str] = None


class ErrorLogItem(BaseModel):
    id: str
    timestamp: datetime
    method: str
    path: str
    status_code: int
    error_type: str
    error_message: str
    traceback: Optional[str] = None
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    company_id: Optional[str] = None
    query_params: Optional[str] = None


class ErrorLogsResponse(BaseModel):
    items: list[ErrorLogItem]
    total: int


class AdminAddRequirementRequest(BaseModel):
    jurisdiction_requirement_id: UUID


class BetaInviteRequest(BaseModel):
    emails: list[EmailStr] = Field(..., min_length=1, max_length=50)


class IndividualInviteRequest(BaseModel):
    email: EmailStr


class MatchaLiteInviteRequest(BaseModel):
    note: Optional[str] = None


class SuspendBody(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class PasswordResetResponse(BaseModel):
    reset_url: str
    expires_in_minutes: int


class TierChangeBody(BaseModel):
    tier: str  # 'resources_free' | 'matcha_lite' | 'matcha_x' | 'matcha_compliance' | 'bespoke' | 'ir_only_self_serve'


class ChargeSummary(BaseModel):
    id: str
    amount: int
    amount_refunded: int
    currency: str
    created: int
    status: str
    description: Optional[str] = None


class RefundBody(BaseModel):
    charge_id: str
    amount_cents: Optional[int] = Field(default=None, ge=1)
    reason: Optional[str] = Field(default=None, max_length=500)
