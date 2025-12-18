from datetime import datetime
from typing import Optional, Any, Literal
from uuid import UUID

from pydantic import BaseModel


InterviewType = Literal["culture", "candidate"]


class InterviewCreate(BaseModel):
    company_id: UUID
    interviewer_name: Optional[str] = None
    interviewer_role: Optional[str] = None  # e.g. "VP Engineering", "HR Director"
    interview_type: InterviewType = "culture"


class Interview(BaseModel):
    id: UUID
    company_id: UUID
    interviewer_name: Optional[str] = None
    interviewer_role: Optional[str] = None
    interview_type: InterviewType = "culture"
    transcript: Optional[str] = None
    raw_culture_data: Optional[dict[str, Any]] = None
    status: str  # pending, in_progress, completed
    created_at: datetime
    completed_at: Optional[datetime] = None


class InterviewResponse(BaseModel):
    id: UUID
    company_id: UUID
    interviewer_name: Optional[str] = None
    interviewer_role: Optional[str] = None
    interview_type: InterviewType = "culture"
    transcript: Optional[str] = None
    raw_culture_data: Optional[dict[str, Any]] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class InterviewStart(BaseModel):
    """Response when starting a new interview session."""
    interview_id: UUID
    websocket_url: str
