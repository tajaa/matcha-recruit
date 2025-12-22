from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr

UserRole = Literal["admin", "client", "candidate"]


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


class CurrentUser(BaseModel):
    id: UUID
    email: str
    role: UserRole
    profile: Optional[AdminProfile | ClientProfile | CandidateProfile] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangeEmailRequest(BaseModel):
    password: str  # Require password confirmation
    new_email: EmailStr


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
