from datetime import datetime, date
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field
from decimal import Decimal

UserRole = Literal["admin", "client", "candidate", "employee", "broker", "creator", "agency", "gumfit_admin"]


class UserBase(BaseModel):
    email: EmailStr
    role: UserRole


class UserCreate(UserBase):
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class TokenPayload(BaseModel):
    sub: str  # user_id
    email: str
    role: UserRole
    exp: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Registration models for each user type
class AdminRegister(BaseModel):
    email: EmailStr
    password: str
    name: str


class ClientRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    company_id: UUID
    phone: Optional[str] = None
    job_title: Optional[str] = None


class CandidateRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None


class EmployeeRegister(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    company_id: UUID
    work_state: Optional[str] = None
    employment_type: Optional[str] = None  # full_time, part_time, contractor
    start_date: Optional[datetime] = None


class BusinessRegister(BaseModel):
    """
    Unified business registration - creates company + first client/admin user.
    This is the recommended way for new businesses to register.
    """
    # Company info
    company_name: str
    industry: Optional[str] = None
    company_size: Optional[str] = None  # e.g., "1-10", "11-50", etc.
    headcount: int = Field(..., ge=1)

    # First admin user info
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None
    job_title: Optional[str] = None

    # Optional invite token for auto-approval
    invite_token: Optional[str] = None


class TestAccountRegister(BaseModel):
    """
    Test account registration - creates an approved company with all feature flags
    enabled and pre-seeded demo data for feature validation.
    """
    company_name: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    email: EmailStr
    password: Optional[str] = None
    name: str
    phone: Optional[str] = None
    job_title: Optional[str] = None


class TestAccountProvisionResponse(BaseModel):
    status: str
    message: str
    company_id: UUID
    company_name: str
    user_id: UUID
    email: str
    password: str
    generated_password: bool = False


# Profile models
class AdminProfile(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    email: str
    created_at: datetime


class ClientProfile(BaseModel):
    id: UUID
    user_id: UUID
    company_id: UUID
    company_name: str
    name: str
    phone: Optional[str]
    job_title: Optional[str]
    email: str
    created_at: datetime


class CandidateProfile(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    skills: Optional[list[str]]
    experience_years: Optional[int]
    created_at: datetime


class EmployeeProfile(BaseModel):
    id: UUID
    user_id: UUID
    company_id: UUID
    company_name: str
    first_name: str
    last_name: str
    email: str
    work_state: Optional[str]
    employment_type: Optional[str]
    start_date: Optional[datetime]
    manager_id: Optional[UUID]
    created_at: datetime


class BrokerProfile(BaseModel):
    id: UUID  # broker_members.id
    user_id: UUID
    broker_id: UUID
    broker_name: str
    broker_slug: str
    branding_mode: Literal["direct", "co_branded", "white_label"] = "direct"
    brand_display_name: Optional[str] = None
    member_role: str
    broker_status: str
    billing_mode: str
    invoice_owner: str
    support_routing: str
    terms_required_version: str
    terms_accepted: bool = False
    terms_accepted_at: Optional[datetime] = None
    created_at: datetime


class CurrentUser(BaseModel):
    id: UUID
    email: str
    role: UserRole
    profile: Optional[AdminProfile | ClientProfile | CandidateProfile | EmployeeProfile | BrokerProfile] = None
    beta_features: dict = {}
    interview_prep_tokens: int = 0
    allowed_interview_roles: list[str] = []


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangeEmailRequest(BaseModel):
    password: str  # Require password confirmation
    new_email: EmailStr


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None


class BrokerTermsAcceptanceRequest(BaseModel):
    terms_version: Optional[str] = None


class BrokerTermsAcceptanceResponse(BaseModel):
    status: str
    broker_id: UUID
    terms_version: str
    accepted_at: datetime


class BrokerClientInviteDetailsResponse(BaseModel):
    valid: bool
    broker_name: str
    company_name: str
    contact_email: EmailStr
    invite_expires_at: datetime


class BrokerClientInviteAcceptRequest(BaseModel):
    password: str
    name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None


class BrokerBrandingRuntimeResponse(BaseModel):
    broker_id: UUID
    broker_slug: str
    broker_name: str
    branding_mode: Literal["direct", "co_branded", "white_label"]
    brand_display_name: str
    brand_legal_name: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    login_subdomain: Optional[str] = None
    custom_login_url: Optional[str] = None
    support_email: Optional[EmailStr] = None
    support_phone: Optional[str] = None
    support_url: Optional[str] = None
    email_from_name: Optional[str] = None
    email_from_address: Optional[EmailStr] = None
    powered_by_badge: bool = True
    hide_matcha_identity: bool = False
    mobile_branding_enabled: bool = False
    theme: dict = Field(default_factory=dict)
    resolved_by: Literal["slug", "subdomain"] = "slug"


# Beta access management models
class CandidateBetaInfo(BaseModel):
    user_id: UUID
    email: str
    name: Optional[str]
    beta_features: dict
    interview_prep_tokens: int
    allowed_interview_roles: list[str] = []
    total_sessions: int = 0
    avg_score: Optional[float] = None
    last_session_at: Optional[datetime] = None


class CandidateBetaListResponse(BaseModel):
    candidates: list[CandidateBetaInfo]
    total: int


class BetaToggleRequest(BaseModel):
    feature: str
    enabled: bool


class TokenAwardRequest(BaseModel):
    amount: int


class AllowedRolesRequest(BaseModel):
    roles: list[str]


class CandidateSessionSummary(BaseModel):
    session_id: UUID
    interview_role: Optional[str]
    duration_minutes: int
    status: str
    created_at: datetime
    response_quality_score: Optional[float] = None
    communication_score: Optional[float] = None
