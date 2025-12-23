"""Job application models for public job board."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class ApplicationStatus(str, Enum):
    NEW = "new"
    REVIEWED = "reviewed"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    HIRED = "hired"


class ApplicationSource(str, Enum):
    DIRECT = "direct"
    GOOGLE_JOBS = "google_jobs"
    INDEED = "indeed"
    LINKEDIN = "linkedin"
    GLASSDOOR = "glassdoor"
    WELLFOUND = "wellfound"
    REMOTEOK = "remoteok"
    OTHER = "other"


class JobApplicationCreate(BaseModel):
    """Schema for submitting a job application."""
    name: str
    email: EmailStr
    phone: Optional[str] = None
    cover_letter: Optional[str] = None
    source: Optional[str] = "direct"


class JobApplication(BaseModel):
    """Full job application model."""
    id: UUID
    position_id: UUID
    candidate_id: UUID
    source: Optional[str] = None
    cover_letter: Optional[str] = None
    status: str = "new"
    created_at: datetime
    updated_at: datetime


class JobApplicationResponse(BaseModel):
    """Response schema with candidate and position info."""
    id: UUID
    position_id: UUID
    position_title: str
    candidate_id: UUID
    candidate_name: str
    candidate_email: str
    source: Optional[str] = None
    cover_letter: Optional[str] = None
    status: str
    created_at: datetime


class ApplicationSubmitResponse(BaseModel):
    """Response after successfully submitting an application."""
    success: bool
    message: str
    application_id: UUID
