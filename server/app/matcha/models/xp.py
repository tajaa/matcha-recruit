"""
Employee Experience (XP) Models

Models for Vibe Checks, eNPS Surveys, and Performance Reviews.
"""
from datetime import datetime, date
from typing import Optional, Literal, Any
from uuid import UUID
from pydantic import BaseModel, Field
from decimal import Decimal


# ================================
# Literal Types
# ================================

VibeFrequency = Literal["daily", "weekly", "biweekly", "monthly"]
ENPSStatus = Literal["draft", "active", "closed", "archived"]
ENPSCategory = Literal["detractor", "passive", "promoter"]
ReviewCycleStatus = Literal["draft", "active", "completed", "archived"]
PerformanceReviewStatus = Literal["pending", "self_submitted", "manager_submitted", "completed", "skipped"]


# ================================
# Vibe Check Models
# ================================

class VibeCheckConfigBase(BaseModel):
    frequency: VibeFrequency = "weekly"
    enabled: bool = True
    is_anonymous: bool = False
    questions: list[dict[str, Any]] = Field(default_factory=list)


class VibeCheckConfigCreate(VibeCheckConfigBase):
    pass


class VibeCheckConfigUpdate(BaseModel):
    frequency: Optional[VibeFrequency] = None
    enabled: Optional[bool] = None
    is_anonymous: Optional[bool] = None
    questions: Optional[list[dict[str, Any]]] = None


class VibeCheckConfigResponse(VibeCheckConfigBase):
    id: UUID
    org_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VibeCheckSubmit(BaseModel):
    mood_rating: int = Field(..., ge=1, le=5, description="Mood rating from 1 (struggling) to 5 (great)")
    comment: Optional[str] = None
    custom_responses: Optional[dict[str, Any]] = None


class VibeCheckResponse(BaseModel):
    id: UUID
    org_id: UUID
    employee_id: Optional[UUID]
    mood_rating: int
    comment: Optional[str]
    custom_responses: Optional[dict[str, Any]]
    sentiment_analysis: Optional[dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class VibeCheckListResponse(BaseModel):
    responses: list[VibeCheckResponse]
    total: int


class VibeAnalytics(BaseModel):
    period: str
    total_responses: int
    avg_mood_rating: Optional[Decimal]
    avg_sentiment_score: Optional[Decimal]
    response_rate: Decimal
    top_themes: list[dict[str, Any]]


# ================================
# eNPS Survey Models
# ================================

class ENPSSurveyBase(BaseModel):
    title: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    is_anonymous: bool = False
    custom_question: Optional[str] = None


class ENPSSurveyCreate(ENPSSurveyBase):
    pass


class ENPSSurveyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[ENPSStatus] = None
    is_anonymous: Optional[bool] = None
    custom_question: Optional[str] = None


class ENPSSurveyResponse(ENPSSurveyBase):
    id: UUID
    org_id: UUID
    status: ENPSStatus
    created_by: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True


class ENPSSurveyListResponse(BaseModel):
    surveys: list[ENPSSurveyResponse]
    total: int


class ENPSSubmit(BaseModel):
    score: int = Field(..., ge=0, le=10, description="NPS score from 0-10")
    reason: Optional[str] = None


class ENPSResponseRecord(BaseModel):
    id: UUID
    survey_id: UUID
    employee_id: Optional[UUID]
    score: int
    reason: Optional[str]
    category: ENPSCategory
    sentiment_analysis: Optional[dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class ENPSResults(BaseModel):
    enps_score: Decimal
    promoters: int
    detractors: int
    passives: int
    total_responses: int
    response_rate: Decimal
    promoter_themes: list[dict[str, Any]]
    detractor_themes: list[dict[str, Any]]
    passive_themes: list[dict[str, Any]]


# ================================
# Performance Review Models
# ================================

class ReviewTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    categories: list[dict[str, Any]]  # [{name, weight, criteria: [{name, description}]}]


class ReviewTemplateCreate(ReviewTemplateBase):
    pass


class ReviewTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    categories: Optional[list[dict[str, Any]]] = None
    is_active: Optional[bool] = None


class ReviewTemplateResponse(ReviewTemplateBase):
    id: UUID
    org_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewTemplateListResponse(BaseModel):
    templates: list[ReviewTemplateResponse]
    total: int


class ReviewCycleBase(BaseModel):
    title: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    template_id: Optional[UUID] = None


class ReviewCycleCreate(ReviewCycleBase):
    pass


class ReviewCycleUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[ReviewCycleStatus] = None
    template_id: Optional[UUID] = None


class ReviewCycleResponse(ReviewCycleBase):
    id: UUID
    org_id: UUID
    status: ReviewCycleStatus
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewCycleListResponse(BaseModel):
    cycles: list[ReviewCycleResponse]
    total: int


class SelfAssessmentSubmit(BaseModel):
    self_ratings: dict[str, Any]  # {category_name: rating}
    self_comments: Optional[str] = None


class ManagerReviewSubmit(BaseModel):
    manager_ratings: dict[str, Any]  # {category_name: rating}
    manager_comments: Optional[str] = None
    manager_overall_rating: Optional[Decimal] = Field(None, ge=0, le=5)


class PerformanceReviewBase(BaseModel):
    employee_id: UUID
    manager_id: UUID


class PerformanceReviewResponse(BaseModel):
    id: UUID
    cycle_id: UUID
    employee_id: UUID
    manager_id: UUID
    status: PerformanceReviewStatus
    self_ratings: Optional[dict[str, Any]]
    self_comments: Optional[str]
    self_submitted_at: Optional[datetime]
    manager_ratings: Optional[dict[str, Any]]
    manager_comments: Optional[str]
    manager_overall_rating: Optional[Decimal]
    manager_submitted_at: Optional[datetime]
    ai_analysis: Optional[dict[str, Any]]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class PerformanceReviewDetail(PerformanceReviewResponse):
    """Extended review detail with employee and manager info."""
    employee_first_name: str
    employee_last_name: str
    employee_email: str
    manager_first_name: str
    manager_last_name: str
    manager_email: str
    template_categories: Optional[list[dict[str, Any]]]


class PerformanceReviewListResponse(BaseModel):
    reviews: list[PerformanceReviewResponse]
    total: int


class ReviewProgress(BaseModel):
    """Summary of review cycle progress."""
    cycle_id: UUID
    total_reviews: int
    pending: int
    self_submitted: int
    manager_submitted: int
    completed: int
    completion_rate: Decimal
