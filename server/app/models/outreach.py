"""Pydantic models for project outreach."""
from datetime import datetime
from typing import Optional
from uuid import UUID
from enum import Enum

from pydantic import BaseModel


class OutreachStatus(str, Enum):
    SENT = "sent"
    OPENED = "opened"
    INTERESTED = "interested"
    DECLINED = "declined"
    SCREENING_STARTED = "screening_started"
    SCREENING_COMPLETE = "screening_complete"
    SCREENING_INVITED = "screening_invited"  # Direct screening invite (skips interest step)


class OutreachSendRequest(BaseModel):
    """Request to send outreach to candidates."""
    candidate_ids: list[UUID]
    custom_message: Optional[str] = None


class OutreachSendResult(BaseModel):
    """Result of sending outreach emails."""
    sent_count: int
    failed_count: int
    skipped_count: int  # Already sent or no email
    errors: list[dict]


class OutreachResponse(BaseModel):
    """Response model for an outreach record."""
    id: UUID
    project_id: UUID
    candidate_id: UUID
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    token: str
    status: str
    email_sent_at: Optional[datetime] = None
    interest_response_at: Optional[datetime] = None
    interview_id: Optional[UUID] = None
    screening_score: Optional[float] = None
    screening_recommendation: Optional[str] = None
    created_at: datetime


class OutreachPublicInfo(BaseModel):
    """Public info shown to candidate on landing page."""
    company_name: str
    position_title: Optional[str] = None
    location: Optional[str] = None
    salary_range: Optional[str] = None
    requirements: Optional[str] = None
    benefits: Optional[str] = None
    status: str  # Current outreach status
    candidate_name: Optional[str] = None


class OutreachInterestResponse(BaseModel):
    """Response after candidate expresses interest."""
    status: str
    message: str
    interview_url: Optional[str] = None


class InterviewStartResponse(BaseModel):
    """Response when starting a screening interview."""
    interview_id: UUID
    websocket_url: str


class ScreeningPublicInfo(BaseModel):
    """Public info shown to candidate on direct screening landing page."""
    company_name: str
    position_title: Optional[str] = None
    location: Optional[str] = None
    salary_range: Optional[str] = None
    requirements: Optional[str] = None
    benefits: Optional[str] = None
    status: str  # Current outreach status
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None  # For email verification
    interview_id: Optional[UUID] = None  # If already started
