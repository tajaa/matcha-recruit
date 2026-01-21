from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr


# Agency types
AgencyType = Literal["talent", "brand", "hybrid"]
VerificationStatus = Literal["pending", "in_review", "verified", "rejected"]
MemberRole = Literal["owner", "admin", "member"]


# Agency models
class AgencyCreate(BaseModel):
    name: str
    agency_type: AgencyType
    description: Optional[str] = None
    website_url: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    industries: Optional[list[str]] = None


class AgencyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    industries: Optional[list[str]] = None


class AgencyResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    agency_type: AgencyType
    description: Optional[str]
    logo_url: Optional[str]
    website_url: Optional[str]
    is_verified: bool
    verification_status: VerificationStatus
    contact_email: Optional[str]
    industries: list[str]
    created_at: datetime
    updated_at: datetime


class AgencyPublicResponse(BaseModel):
    """Public agency profile for discovery."""
    id: UUID
    name: str
    slug: str
    agency_type: AgencyType
    description: Optional[str]
    logo_url: Optional[str]
    website_url: Optional[str]
    is_verified: bool
    industries: list[str]


# Member models
class AgencyMemberInvite(BaseModel):
    email: EmailStr
    role: MemberRole = "member"
    title: Optional[str] = None


class AgencyMemberUpdate(BaseModel):
    role: Optional[MemberRole] = None
    title: Optional[str] = None
    is_active: Optional[bool] = None


class AgencyMemberResponse(BaseModel):
    id: UUID
    agency_id: UUID
    user_id: UUID
    email: str
    role: MemberRole
    title: Optional[str]
    is_active: bool
    invited_at: datetime
    joined_at: Optional[datetime]


# Agency with member context
class AgencyWithMembership(BaseModel):
    agency: AgencyResponse
    membership: AgencyMemberResponse
    member_count: int
    active_deals_count: int
