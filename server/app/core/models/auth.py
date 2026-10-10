from datetime import datetime, date
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field
from decimal import Decimal

UserRole = Literal["admin", "client", "candidate", "employee", "creator", "agency", "gumfit_admin", "individual"]


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
    # Business (non-personal) company name. Null for personal/individual,
    # admin, and other roles — the desktop top bar shows it for business
    # accounts and falls back to email otherwise.
    company_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    client: Optional[Literal["ios_schedule"]] = None
    device_name: Optional[str] = Field(default=None, max_length=200)
    # What the signing-in Matcha Schedule build can do. A business admin needs
    # "manage": an older build would get a session minted and then throw it
    # away, leaving an orphan device row and the wrong error on screen.
    capabilities: list[Literal["manage"]] = Field(default_factory=list, max_length=8)


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
    iat: Optional[int] = None  # issued-at (epoch); used for session revocation
    iat_ms: Optional[int] = None  # issued-at (epoch ms); exact revocation compare
    session_started_at: Optional[int] = None  # preserved across refresh rotation
    token_type: Optional[str] = None  # "access" or "refresh"
    sid: Optional[str] = None  # mobile device session id
    cl: Optional[str] = None  # mobile client identifier
    gen: Optional[int] = None  # mobile refresh generation; rotation is compare-and-swap


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class MobileLogoutRequest(RefreshTokenRequest):
    push_token: Optional[str] = None  # APNs token to drop alongside the session


# Registration models for each user type
class AdminRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str


class ClientRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    company_id: UUID
    phone: Optional[str] = None
    job_title: Optional[str] = None


class CandidateRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    phone: Optional[str] = None


class BusinessRegister(BaseModel):
    """
    Unified business registration - creates company + first client/admin user.
    This is the recommended way for new businesses to register.
    """
    # Company info
    company_name: str
    industry: Optional[str] = None
    company_size: Optional[str] = None  # e.g., "1-10", "11-50", etc.
    healthcare_specialties: Optional[list[str]] = None
    headcount: int = Field(..., ge=1)
    # Number of jurisdictions the company operates in. Only collected on the
    # Matcha Compliance signup (/compliance/signup) — drives the per-jurisdiction
    # pricing component. Optional/None on every other tier.
    jurisdiction_count: Optional[int] = None
    # Signup-time billing quantity for custom products priced per location.
    # Persisted separately from actual business_locations, which do not exist
    # yet when the initial subscription checkout is created.
    location_count: Optional[int] = Field(default=None, ge=1)

    # First admin user info
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    phone: Optional[str] = None
    job_title: Optional[str] = None

    # Optional invite token for auto-approval
    invite_token: Optional[str] = None
    # Admin-generated invite token — activates Matcha Lite immediately on signup
    lite_invite_token: Optional[str] = None
    # Signup-time choice on the SAME /lite/signup page/checkout as standard
    # matcha_lite (not a separate product): skips the employee roster (no
    # CSV/HRIS import, no OSHA logs) for companies that just want incident
    # reporting. Only consulted when tier == "matcha_lite"; routes to
    # signup_source = "matcha_lite_essentials" instead of "matcha_lite".
    lite_essentials: bool = False

    # Self-serve product tier. "ir_only" = Matcha IR free-beta signup
    # (auto-approve, only `incidents` feature on, slim IR layout).
    # "matcha_lite" = paid entry IR/HR bundle (headcount-priced Stripe).
    # "matcha_x" = paid mid tier — clone of matcha_lite at Lite parity,
    # branded between Lite and the full platform (extra modules layered later).
    # "matcha_compliance" = standalone self-serve Compliance product
    # (headcount + jurisdiction-priced Stripe; webhook flips the full
    # `compliance` flag). "resources_free" = free resources hub. Anything
    # "custom_product" = an admin-composed product from the /admin/products
    # builder; `product_slug` names which one (signup_source becomes
    # 'product:<slug>'). Anything else / None = bespoke sales-led path
    # (existing behavior).
    tier: Optional[str] = None

    # Slug of the admin-composed product being signed up for. Required when
    # tier == "custom_product", ignored otherwise.
    product_slug: Optional[str] = None


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
    seeded_manager_email: Optional[str] = None
    seeded_employee_email: Optional[str] = None
    seeded_portal_password: Optional[str] = None


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


class CurrentUser(BaseModel):
    id: UUID
    email: str
    role: UserRole
    profile: Optional[AdminProfile | ClientProfile | CandidateProfile | EmployeeProfile] = None
    beta_features: dict = {}
    interview_prep_tokens: int = 0
    allowed_interview_roles: list[str] = []
    device_session_id: Optional[UUID] = None  # set for Matcha Schedule mobile bearers


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ChangeEmailRequest(BaseModel):
    password: str  # Require password confirmation
    new_email: EmailStr


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None


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
