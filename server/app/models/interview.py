from datetime import datetime
from typing import Optional, Any, Literal
from uuid import UUID

from pydantic import BaseModel


InterviewType = Literal["culture", "candidate", "screening", "tutor_interview", "tutor_language"]


# Conversation Analysis Models
class CoverageDetail(BaseModel):
    covered: bool
    depth: Literal["deep", "shallow", "none"]
    evidence: Optional[str] = None


class CoverageCompleteness(BaseModel):
    overall_score: int  # 0-100
    dimensions_covered: list[str]
    dimensions_missed: list[str]
    coverage_details: dict[str, CoverageDetail]


class ResponseAnalysisItem(BaseModel):
    question_summary: str
    response_quality: Literal["specific", "somewhat_specific", "vague", "shallow"]  # shallow added for LLM variance
    actionability: Literal["high", "medium", "low"]
    notes: Optional[str] = None


class ResponseDepth(BaseModel):
    overall_score: int  # 0-100
    specific_examples_count: int
    vague_responses_count: int
    response_analysis: list[ResponseAnalysisItem]


class MissedOpportunity(BaseModel):
    topic: str
    suggested_followup: str
    reason: str


class PromptSuggestion(BaseModel):
    category: str
    current_behavior: str
    suggested_improvement: str
    priority: Literal["high", "medium", "low"]


class ConversationAnalysis(BaseModel):
    coverage_completeness: CoverageCompleteness
    response_depth: ResponseDepth
    missed_opportunities: list[MissedOpportunity]
    prompt_improvement_suggestions: list[PromptSuggestion]
    interview_summary: str
    analyzed_at: datetime


# Screening Analysis Models
class ScreeningAttribute(BaseModel):
    score: float  # 0-100
    evidence: list[str]
    notes: Optional[str] = None


class ScreeningAnalysis(BaseModel):
    communication_clarity: ScreeningAttribute
    engagement_energy: ScreeningAttribute
    critical_thinking: ScreeningAttribute
    professionalism: ScreeningAttribute
    overall_score: float  # 0-100
    recommendation: Literal["strong_pass", "pass", "borderline", "fail"]
    summary: str
    analyzed_at: datetime


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
    conversation_analysis: Optional[ConversationAnalysis] = None
    screening_analysis: Optional[ScreeningAnalysis] = None
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
    conversation_analysis: Optional[ConversationAnalysis] = None
    screening_analysis: Optional[ScreeningAnalysis] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class InterviewStart(BaseModel):
    """Response when starting a new interview session."""
    interview_id: UUID
    websocket_url: str


class TutorSessionCreate(BaseModel):
    """Request to create a tutor session."""
    mode: Literal["interview_prep", "language_test"]
    language: Optional[Literal["en", "es"]] = None  # Required for language_test mode
