from datetime import datetime
from typing import Optional
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, EmailStr


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSING = "closing"  # Atomically set when close workflow is enqueued; prevents duplicate runs
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CandidateStage(str, Enum):
    INITIAL = "initial"
    SCREENING = "screening"
    INTERVIEW = "interview"
    FINALIST = "finalist"
    PLACED = "placed"
    REJECTED = "rejected"


# Project models
class ProjectCreate(BaseModel):
    company_name: str
    name: str
    company_id: Optional[UUID] = None
    position_title: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_hidden: bool = False
    is_public: bool = False
    description: Optional[str] = None
    currency: str = "USD"
    benefits: Optional[str] = None
    requirements: Optional[str] = None
    closing_date: Optional[datetime] = None
    status: ProjectStatus = ProjectStatus.DRAFT
    notes: Optional[str] = None


class ProjectUpdate(BaseModel):
    company_name: Optional[str] = None
    name: Optional[str] = None
    company_id: Optional[UUID] = None
    position_title: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_hidden: Optional[bool] = None
    is_public: Optional[bool] = None
    description: Optional[str] = None
    currency: Optional[str] = None
    benefits: Optional[str] = None
    requirements: Optional[str] = None
    closing_date: Optional[datetime] = None
    status: Optional[ProjectStatus] = None
    notes: Optional[str] = None


class ProjectResponse(BaseModel):
    id: UUID
    company_name: str
    name: str
    company_id: Optional[UUID] = None
    position_title: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_hidden: bool = False
    is_public: bool = False
    description: Optional[str] = None
    currency: str = "USD"
    benefits: Optional[str] = None
    requirements: Optional[str] = None
    closing_date: Optional[datetime] = None
    status: str
    notes: Optional[str] = None
    candidate_count: int = 0
    application_count: int = 0
    created_at: datetime
    updated_at: datetime


# Project Candidate models
class ProjectCandidateAdd(BaseModel):
    candidate_id: UUID
    stage: CandidateStage = CandidateStage.INITIAL
    notes: Optional[str] = None


class ProjectCandidateBulkAdd(BaseModel):
    candidate_ids: list[UUID]
    stage: CandidateStage = CandidateStage.INITIAL


class ProjectCandidateUpdate(BaseModel):
    stage: Optional[CandidateStage] = None
    notes: Optional[str] = None


class ProjectCandidateResponse(BaseModel):
    id: UUID
    project_id: UUID
    candidate_id: UUID
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_phone: Optional[str] = None
    candidate_skills: list[str] = []
    candidate_experience_years: Optional[int] = None
    stage: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# Application models (public job applications tied to a project)
class ApplicationStatus(str, Enum):
    NEW = "new"
    AI_SCREENING = "ai_screening"
    RECOMMENDED = "recommended"
    REVIEW_REQUIRED = "review_required"
    NOT_RECOMMENDED = "not_recommended"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ApplicationResponse(BaseModel):
    id: UUID
    project_id: UUID
    candidate_id: UUID
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_skills: list[str] = []
    status: str
    ai_score: Optional[float] = None
    ai_recommendation: Optional[str] = None
    ai_notes: Optional[str] = None
    source: str = "direct"
    cover_letter: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BulkAcceptResponse(BaseModel):
    accepted: int
    skipped: int
    errors: list[str] = []


class PublicProjectInfo(BaseModel):
    id: UUID
    company_name: str
    position_title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_hidden: bool = False
    currency: str = "USD"
    requirements: Optional[str] = None
    benefits: Optional[str] = None
    closing_date: Optional[datetime] = None
