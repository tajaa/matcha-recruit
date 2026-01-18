from datetime import datetime, date
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr
from decimal import Decimal

UserRole = Literal["admin", "client", "candidate", "employee", "creator", "agency"]


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


class CreatorRegister(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    bio: Optional[str] = None
    niches: Optional[list[str]] = None
    social_handles: Optional[dict] = None  # {"youtube": "handle", "tiktok": "handle", ...}


class AgencyRegister(BaseModel):
    email: EmailStr
    password: str
    agency_name: str
    agency_type: str  # talent, brand, hybrid
    description: Optional[str] = None
    website_url: Optional[str] = None
    industries: Optional[list[str]] = None


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


class CreatorProfile(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str
    bio: Optional[str]
    profile_image_url: Optional[str]
    niches: list[str]
    social_handles: dict
    audience_demographics: dict
    metrics: dict
    is_verified: bool
    is_public: bool
    email: str
    created_at: datetime


class AgencyProfile(BaseModel):
    id: UUID
    user_id: UUID  # Owner's user_id
    agency_name: str
    slug: str
    agency_type: str
    description: Optional[str]
    logo_url: Optional[str]
    website_url: Optional[str]
    is_verified: bool
    contact_email: Optional[str]
    industries: list[str]
    member_role: str  # The current user's role in the agency
    email: str
    created_at: datetime


class CurrentUser(BaseModel):
    id: UUID
    email: str
    role: UserRole
    profile: Optional[AdminProfile | ClientProfile | CandidateProfile | EmployeeProfile | CreatorProfile | AgencyProfile] = None
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
