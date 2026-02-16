from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr

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


class CreatorRegister(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    bio: Optional[str] = None
    niches: Optional[list[str]] = None
    social_handles: Optional[dict] = None


class AgencyRegister(BaseModel):
    email: EmailStr
    password: str
    agency_name: str
    agency_type: str  # talent, brand, hybrid
    description: Optional[str] = None
    website_url: Optional[str] = None
    industries: Optional[list[str]] = None


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
    user_id: UUID
    agency_name: str
    slug: str
    agency_type: str
    description: Optional[str]
    logo_url: Optional[str]
    website_url: Optional[str]
    is_verified: bool
    contact_email: Optional[str]
    industries: list[str]
    member_role: str
    email: str
    created_at: datetime


class CurrentUser(BaseModel):
    id: UUID
    email: str
    role: UserRole
    profile: Optional[CreatorProfile | AgencyProfile] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangeEmailRequest(BaseModel):
    password: str
    new_email: EmailStr
