from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


MobilityVisibility = Literal["private", "hr_only", "manager_visible"]
OpportunityType = Literal["role", "project"]
OpportunityStatus = Literal["draft", "active", "closed"]
MatchStatus = Literal["suggested", "saved", "dismissed", "applied"]
ApplicationStatus = Literal["new", "in_review", "shortlisted", "aligned", "closed"]


class EmployeeCareerProfileUpdateRequest(BaseModel):
    target_roles: Optional[list[str]] = None
    target_departments: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    interests: Optional[list[str]] = None
    mobility_opt_in: Optional[bool] = None


class EmployeeCareerProfileResponse(BaseModel):
    id: UUID
    employee_id: UUID
    org_id: UUID
    target_roles: list[str]
    target_departments: list[str]
    skills: list[str]
    interests: list[str]
    mobility_opt_in: bool
    visibility: MobilityVisibility
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MobilityFeedItem(BaseModel):
    opportunity_id: UUID
    type: OpportunityType
    title: str
    department: Optional[str] = None
    description: Optional[str] = None
    match_score: Optional[float] = None
    status: MatchStatus = "suggested"
    reasons: Optional[dict[str, Any]] = None


class MobilityFeedResponse(BaseModel):
    items: list[MobilityFeedItem]
    total: int


class MobilityOpportunityActionResponse(BaseModel):
    opportunity_id: UUID
    status: MatchStatus


class MobilityApplicationCreateRequest(BaseModel):
    employee_notes: Optional[str] = Field(default=None, max_length=500)


class MobilityApplicationResponse(BaseModel):
    application_id: UUID
    status: ApplicationStatus
    submitted_at: datetime
    manager_notified: bool


class InternalOpportunityCreateRequest(BaseModel):
    type: OpportunityType
    position_id: Optional[UUID] = None
    title: str
    department: Optional[str] = None
    description: Optional[str] = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    duration_weeks: Optional[int] = None
    status: OpportunityStatus = "draft"


class InternalOpportunityUpdateRequest(BaseModel):
    type: Optional[OpportunityType] = None
    position_id: Optional[UUID] = None
    title: Optional[str] = None
    department: Optional[str] = None
    description: Optional[str] = None
    required_skills: Optional[list[str]] = None
    preferred_skills: Optional[list[str]] = None
    duration_weeks: Optional[int] = None
    status: Optional[OpportunityStatus] = None


class InternalOpportunityResponse(BaseModel):
    id: UUID
    org_id: UUID
    type: OpportunityType
    position_id: Optional[UUID] = None
    title: str
    department: Optional[str] = None
    description: Optional[str] = None
    required_skills: list[str]
    preferred_skills: list[str]
    duration_weeks: Optional[int] = None
    status: OpportunityStatus
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InternalMobilityApplicationAdminResponse(BaseModel):
    id: UUID
    employee_id: UUID
    employee_name: str
    employee_email: str
    opportunity_id: UUID
    opportunity_title: str
    opportunity_type: OpportunityType
    status: ApplicationStatus
    employee_notes: Optional[str] = None
    submitted_at: datetime
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    manager_notified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class InternalMobilityApplicationUpdateRequest(BaseModel):
    status: Optional[ApplicationStatus] = None
    manager_notified: Optional[bool] = None
