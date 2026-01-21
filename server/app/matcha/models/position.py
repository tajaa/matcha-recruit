from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, field_validator


class EmploymentType(str, Enum):
    FULL_TIME = "full-time"
    PART_TIME = "part-time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"


class ExperienceLevel(str, Enum):
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"


class RemotePolicy(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class PositionStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    DRAFT = "draft"


class PositionCreate(BaseModel):
    """Schema for creating a new position."""
    company_id: UUID
    title: str

    # Basic fields
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    location: Optional[str] = None
    employment_type: Optional[EmploymentType] = None

    # Detailed fields
    requirements: Optional[list[str]] = None
    responsibilities: Optional[list[str]] = None
    required_skills: Optional[list[str]] = None
    preferred_skills: Optional[list[str]] = None
    experience_level: Optional[ExperienceLevel] = None
    benefits: Optional[list[str]] = None

    # Comprehensive fields
    department: Optional[str] = None
    reporting_to: Optional[str] = None
    remote_policy: Optional[RemotePolicy] = None
    visa_sponsorship: bool = False

    @field_validator('salary_max')
    @classmethod
    def validate_salary_range(cls, v, info):
        if v is not None and info.data.get('salary_min') is not None:
            if v < info.data['salary_min']:
                raise ValueError('salary_max must be greater than or equal to salary_min')
        return v


class PositionUpdate(BaseModel):
    """Schema for updating a position."""
    title: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    requirements: Optional[list[str]] = None
    responsibilities: Optional[list[str]] = None
    required_skills: Optional[list[str]] = None
    preferred_skills: Optional[list[str]] = None
    experience_level: Optional[ExperienceLevel] = None
    benefits: Optional[list[str]] = None
    department: Optional[str] = None
    reporting_to: Optional[str] = None
    remote_policy: Optional[RemotePolicy] = None
    visa_sponsorship: Optional[bool] = None
    status: Optional[PositionStatus] = None


class Position(BaseModel):
    """Full position model from database."""
    id: UUID
    company_id: UUID
    title: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    location: Optional[str] = None
    employment_type: Optional[str] = None
    requirements: Optional[list[str]] = None
    responsibilities: Optional[list[str]] = None
    required_skills: Optional[list[str]] = None
    preferred_skills: Optional[list[str]] = None
    experience_level: Optional[str] = None
    benefits: Optional[list[str]] = None
    department: Optional[str] = None
    reporting_to: Optional[str] = None
    remote_policy: Optional[str] = None
    visa_sponsorship: bool = False
    status: str = "active"
    show_on_job_board: bool = False
    created_at: datetime
    updated_at: datetime


class PositionResponse(BaseModel):
    """Schema for position responses (includes company name)."""
    id: UUID
    company_id: UUID
    title: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    location: Optional[str] = None
    employment_type: Optional[str] = None
    requirements: Optional[list[str]] = None
    responsibilities: Optional[list[str]] = None
    required_skills: Optional[list[str]] = None
    preferred_skills: Optional[list[str]] = None
    experience_level: Optional[str] = None
    benefits: Optional[list[str]] = None
    department: Optional[str] = None
    reporting_to: Optional[str] = None
    remote_policy: Optional[str] = None
    visa_sponsorship: bool = False
    status: str = "active"
    show_on_job_board: bool = False
    created_at: datetime
    updated_at: datetime
    company_name: Optional[str] = None


class PositionMatchResult(BaseModel):
    """Position match result from database."""
    id: UUID
    position_id: UUID
    candidate_id: UUID
    overall_score: float
    skills_match_score: float
    experience_match_score: float
    culture_fit_score: float
    match_reasoning: Optional[str] = None
    skills_breakdown: Optional[dict[str, Any]] = None
    experience_breakdown: Optional[dict[str, Any]] = None
    culture_fit_breakdown: Optional[dict[str, Any]] = None
    created_at: datetime


class PositionMatchResultResponse(BaseModel):
    """Schema for position match results with candidate info."""
    id: UUID
    position_id: UUID
    candidate_id: UUID
    candidate_name: Optional[str] = None
    overall_score: float
    skills_match_score: float
    experience_match_score: float
    culture_fit_score: float
    match_reasoning: Optional[str] = None
    skills_breakdown: Optional[dict[str, Any]] = None
    experience_breakdown: Optional[dict[str, Any]] = None
    culture_fit_breakdown: Optional[dict[str, Any]] = None
    created_at: datetime
