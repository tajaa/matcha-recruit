from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel


class CompanyCreate(BaseModel):
    name: str
    industry: Optional[str] = None
    size: Optional[str] = None  # startup, mid, enterprise
    ir_guidance_blurb: Optional[str] = None
    headquarters_state: Optional[str] = None
    headquarters_city: Optional[str] = None
    work_arrangement: Optional[str] = None
    default_employment_type: Optional[str] = None
    benefits_summary: Optional[str] = None
    pto_policy_summary: Optional[str] = None
    compensation_notes: Optional[str] = None
    company_values: Optional[str] = None
    ai_guidance_notes: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    ir_guidance_blurb: Optional[str] = None
    headquarters_state: Optional[str] = None
    headquarters_city: Optional[str] = None
    work_arrangement: Optional[str] = None
    default_employment_type: Optional[str] = None
    benefits_summary: Optional[str] = None
    pto_policy_summary: Optional[str] = None
    compensation_notes: Optional[str] = None
    company_values: Optional[str] = None
    ai_guidance_notes: Optional[str] = None


class Company(BaseModel):
    id: UUID
    name: str
    industry: Optional[str] = None
    size: Optional[str] = None
    ir_guidance_blurb: Optional[str] = None
    logo_url: Optional[str] = None
    headquarters_state: Optional[str] = None
    headquarters_city: Optional[str] = None
    work_arrangement: Optional[str] = None
    default_employment_type: Optional[str] = None
    benefits_summary: Optional[str] = None
    pto_policy_summary: Optional[str] = None
    compensation_notes: Optional[str] = None
    company_values: Optional[str] = None
    ai_guidance_notes: Optional[str] = None
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
    logo_url: Optional[str] = None
    headquarters_state: Optional[str] = None
    headquarters_city: Optional[str] = None
    work_arrangement: Optional[str] = None
    default_employment_type: Optional[str] = None
    benefits_summary: Optional[str] = None
    pto_policy_summary: Optional[str] = None
    compensation_notes: Optional[str] = None
    company_values: Optional[str] = None
    ai_guidance_notes: Optional[str] = None
    created_at: datetime
    culture_profile: Optional[dict[str, Any]] = None
    interview_count: int = 0
