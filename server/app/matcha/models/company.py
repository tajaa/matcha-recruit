from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel


class CompanyCreate(BaseModel):
    name: str
    industry: Optional[str] = None
    size: Optional[str] = None  # startup, mid, enterprise
    ir_guidance_blurb: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    ir_guidance_blurb: Optional[str] = None


class Company(BaseModel):
    id: UUID
    name: str
    industry: Optional[str] = None
    size: Optional[str] = None
    ir_guidance_blurb: Optional[str] = None
    created_at: datetime


class CultureProfile(BaseModel):
    id: UUID
    company_id: UUID
    profile_data: dict[str, Any]
    last_updated: datetime


class CompanyResponse(BaseModel):
    id: UUID
    name: str
    industry: Optional[str] = None
    size: Optional[str] = None
    ir_guidance_blurb: Optional[str] = None
    created_at: datetime
    culture_profile: Optional[dict[str, Any]] = None
    interview_count: int = 0
