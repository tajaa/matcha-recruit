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


# Tutor Interview Analysis Models (for interview prep mode)
class TutorResponseBreakdown(BaseModel):
    question: str
    quality: Literal["specific", "somewhat_specific", "vague"]
    used_examples: bool
    depth: Literal["excellent", "good", "shallow"]
    feedback: str


class TutorResponseQuality(BaseModel):
    overall_score: int  # 0-100
    specificity_score: int
    example_usage_score: int
    depth_score: int
    breakdown: list[TutorResponseBreakdown]


class TutorCommunicationSkills(BaseModel):
    overall_score: int  # 0-100
    clarity_score: int
    confidence_score: int
    professionalism_score: int
    engagement_score: int
    notes: Optional[str] = None


class TutorMissedOpportunity(BaseModel):
    topic: str
    suggestion: str


class TutorContentCoverage(BaseModel):
    topics_covered: list[str]
    missed_opportunities: list[TutorMissedOpportunity]
    follow_up_depth: Literal["excellent", "good", "shallow"]


class TutorImprovementSuggestion(BaseModel):
    area: str
    suggestion: str
    priority: Literal["high", "medium", "low"]


class TutorInterviewAnalysis(BaseModel):
    response_quality: TutorResponseQuality
    communication_skills: TutorCommunicationSkills
    content_coverage: TutorContentCoverage
    improvement_suggestions: list[TutorImprovementSuggestion]
    session_summary: str
    analyzed_at: datetime


# Tutor Language Analysis Models (for language test mode)
class TutorFluencyPace(BaseModel):
    overall_score: int  # 0-100
    speaking_speed: Literal["natural", "too_fast", "too_slow", "varies"]
    pause_frequency: Literal["rare", "occasional", "frequent"]
    filler_word_count: int
    filler_words_used: list[str]
    flow_rating: Literal["excellent", "good", "choppy", "poor"]
    notes: Optional[str] = None


class TutorVocabulary(BaseModel):
    overall_score: int  # 0-100
    variety_score: int
    appropriateness_score: int
    complexity_level: Literal["basic", "intermediate", "advanced"]
    notable_good_usage: list[str]
    suggestions: list[str]


class TutorGrammarError(BaseModel):
    error: str
    correction: str
    type: str  # tense, agreement, word_order, article, preposition, other


class TutorGrammar(BaseModel):
    overall_score: int  # 0-100
    sentence_structure_score: int
    tense_usage_score: int
    common_errors: list[TutorGrammarError]
    notes: Optional[str] = None


class TutorProficiencyLevel(BaseModel):
    level: Literal["A1", "A2", "B1", "B2", "C1", "C2"]
    level_description: str
    strengths: list[str]
    areas_to_improve: list[str]


class TutorPracticeSuggestion(BaseModel):
    skill: str
    exercise: str
    priority: Literal["high", "medium", "low"]


class TutorLanguageAnalysis(BaseModel):
    fluency_pace: TutorFluencyPace
    vocabulary: TutorVocabulary
    grammar: TutorGrammar
    overall_proficiency: TutorProficiencyLevel
    practice_suggestions: list[TutorPracticeSuggestion]
    session_summary: str
    analyzed_at: datetime
    language: str  # "en" or "es"


class InterviewCreate(BaseModel):
    company_id: UUID
    interviewer_name: Optional[str] = None
    interviewer_role: Optional[str] = None  # e.g. "VP Engineering", "HR Director"
    interview_type: InterviewType = "culture"


class Interview(BaseModel):
    id: UUID
    company_id: Optional[UUID] = None  # None for tutor sessions
    interviewer_name: Optional[str] = None
    interviewer_role: Optional[str] = None
    interview_type: InterviewType = "culture"
    transcript: Optional[str] = None
    raw_culture_data: Optional[dict[str, Any]] = None
    conversation_analysis: Optional[ConversationAnalysis] = None
    screening_analysis: Optional[ScreeningAnalysis] = None
    tutor_analysis: Optional[dict[str, Any]] = None  # TutorInterviewAnalysis or TutorLanguageAnalysis
    status: str  # pending, in_progress, analyzing, completed
    created_at: datetime
    completed_at: Optional[datetime] = None


class InterviewResponse(BaseModel):
    id: UUID
    company_id: Optional[UUID] = None  # None for tutor sessions
    interviewer_name: Optional[str] = None
    interviewer_role: Optional[str] = None
    interview_type: InterviewType = "culture"
    transcript: Optional[str] = None
    raw_culture_data: Optional[dict[str, Any]] = None
    conversation_analysis: Optional[ConversationAnalysis] = None
    screening_analysis: Optional[ScreeningAnalysis] = None
    tutor_analysis: Optional[dict[str, Any]] = None  # TutorInterviewAnalysis or TutorLanguageAnalysis
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class InterviewStart(BaseModel):
    """Response when starting a new interview session."""
    interview_id: UUID
    websocket_url: str
    ws_auth_token: Optional[str] = None
    max_session_duration_seconds: Optional[int] = None  # Session time limit


class TutorSessionCreate(BaseModel):
    """Request to create a tutor session."""
    mode: Literal["interview_prep", "language_test"]
    language: Optional[Literal["en", "es"]] = None  # Required for language_test mode
    duration_minutes: Optional[Literal[2, 5, 8]] = None  # Session duration: 2, 5, or 8 minutes
    interview_role: Optional[str] = None  # For interview_prep: role being interviewed for


class TutorSessionSummary(BaseModel):
    """Summary of a tutor session for list views."""
    id: UUID
    interview_type: Literal["tutor_interview", "tutor_language"]
    language: Optional[str] = None  # For tutor_language sessions
    status: str
    overall_score: Optional[int] = None  # Extracted from tutor_analysis
    created_at: datetime
    completed_at: Optional[datetime] = None


class TutorSessionDetail(BaseModel):
    """Full tutor session with analysis."""
    id: UUID
    interview_type: Literal["tutor_interview", "tutor_language"]
    language: Optional[str] = None
    transcript: Optional[str] = None
    tutor_analysis: Optional[dict[str, Any]] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class TutorMetricsAggregate(BaseModel):
    """Aggregate metrics across tutor sessions."""
    interview_prep: dict[str, Any]  # Stats for tutor_interview
    language_test: dict[str, Any]  # Stats for tutor_language


class TutorProgressDataPoint(BaseModel):
    """A single data point for progress tracking."""
    session_id: UUID
    date: datetime
    fluency_score: Optional[int] = None
    grammar_score: Optional[int] = None
    vocabulary_score: Optional[int] = None
    proficiency_level: Optional[str] = None


class TutorProgressResponse(BaseModel):
    """Progress data over time for charting."""
    sessions: list[TutorProgressDataPoint]
    language: Optional[str] = None


class TutorSessionComparison(BaseModel):
    """Comparison of current session to previous sessions."""
    current_fluency: Optional[int] = None
    current_grammar: Optional[int] = None
    current_vocabulary: Optional[int] = None
    avg_previous_fluency: Optional[float] = None
    avg_previous_grammar: Optional[float] = None
    avg_previous_vocabulary: Optional[float] = None
    previous_session_count: int
    fluency_change: Optional[float] = None
    grammar_change: Optional[float] = None
    vocabulary_change: Optional[float] = None


class VocabularyWord(BaseModel):
    """A vocabulary word used or suggested."""
    word: str
    category: Optional[str] = None
    used_correctly: Optional[bool] = None
    context: Optional[str] = None
    correction: Optional[str] = None
    difficulty: Optional[str] = None
    times_used: int = 1


class VocabularySuggestion(BaseModel):
    """A suggested vocabulary word to learn."""
    word: str
    meaning: Optional[str] = None
    example: Optional[str] = None
    difficulty: Optional[str] = None


class TutorVocabularyStats(BaseModel):
    """Vocabulary statistics across sessions."""
    total_unique_words: int
    mastered_words: list[VocabularyWord]
    words_to_review: list[VocabularyWord]
    suggested_vocabulary: list[VocabularySuggestion]
    language: str
