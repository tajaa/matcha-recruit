from datetime import datetime
from typing import Optional
from uuid import UUID
from enum import Enum

from pydantic import BaseModel


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
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
    position_title: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    benefits: Optional[str] = None
    requirements: Optional[str] = None
    status: ProjectStatus = ProjectStatus.DRAFT
    notes: Optional[str] = None


class ProjectUpdate(BaseModel):
    company_name: Optional[str] = None
    name: Optional[str] = None
    position_title: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    benefits: Optional[str] = None
    requirements: Optional[str] = None
    status: Optional[ProjectStatus] = None
    notes: Optional[str] = None


class ProjectResponse(BaseModel):
    id: UUID
    company_name: str
    name: str
    position_title: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    benefits: Optional[str] = None
    requirements: Optional[str] = None
    status: str
    notes: Optional[str] = None
    candidate_count: int = 0
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
