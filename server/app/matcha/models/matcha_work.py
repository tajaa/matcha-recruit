from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class OnboardingEmployee(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    work_email: Optional[str] = None
    personal_email: Optional[str] = None
    work_state: Optional[str] = None
    employment_type: Optional[str] = None  # full-time, part-time, contractor
    start_date: Optional[str] = None  # YYYY-MM-DD
    address: Optional[str] = None
    status: Optional[str] = None  # pending, created, provisioning, done, error
    error: Optional[str] = None
    employee_id: Optional[str] = None  # set after creation
    provisioning_results: Optional[dict] = None


class OnboardingDocument(BaseModel):
    """Incremental onboarding state — builds turn by turn as employees are collected."""

    employees: Optional[list[OnboardingEmployee]] = None
    company_name: Optional[str] = None
    default_start_date: Optional[str] = None
    default_employment_type: Optional[str] = None
    default_work_state: Optional[str] = None
    batch_status: Optional[str] = None  # collecting, ready, processing, complete


class OfferLetterDocument(BaseModel):
    """Incremental document state — all fields Optional since it builds turn by turn."""

    candidate_name: Optional[str] = None
    position_title: Optional[str] = None
    company_name: Optional[str] = None
    salary: Optional[str] = None
    bonus: Optional[str] = None
    stock_options: Optional[str] = None
    start_date: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    benefits: Optional[str] = None
    manager_name: Optional[str] = None
    manager_title: Optional[str] = None
    expiration_date: Optional[str] = None
    # Structured benefits
    benefits_medical: Optional[bool] = None
    benefits_medical_coverage: Optional[int] = None
    benefits_medical_waiting_days: Optional[int] = None
    benefits_dental: Optional[bool] = None
    benefits_vision: Optional[bool] = None
    benefits_401k: Optional[bool] = None
    benefits_401k_match: Optional[str] = None
    benefits_wellness: Optional[str] = None
    benefits_pto_vacation: Optional[bool] = None
    benefits_pto_sick: Optional[bool] = None
    benefits_holidays: Optional[bool] = None
    benefits_other: Optional[str] = None
    # Contingencies
    contingency_background_check: Optional[bool] = None
    contingency_credit_check: Optional[bool] = None
    contingency_drug_screening: Optional[bool] = None
    # Company logo
    company_logo_url: Optional[str] = None
    # Salary range
    salary_range_min: Optional[float] = None
    salary_range_max: Optional[float] = None
    candidate_email: Optional[str] = None
    recipient_emails: Optional[list[str]] = None


class ReviewDocument(BaseModel):
    """Incremental one-off anonymized review state."""

    review_title: Optional[str] = None
    review_subject: Optional[str] = None
    context: Optional[str] = None
    accomplishments: Optional[str] = None
    strengths: Optional[str] = None
    growth_areas: Optional[str] = None
    next_steps: Optional[str] = None
    summary: Optional[str] = None
    overall_rating: Optional[int] = None
    anonymized: Optional[bool] = None
    recipient_emails: Optional[list[str]] = None
    review_request_statuses: Optional[list[dict]] = None
    review_expected_responses: Optional[int] = None
    review_received_responses: Optional[int] = None
    review_pending_responses: Optional[int] = None
    review_last_sent_at: Optional[str] = None


class WorkbookSection(BaseModel):
    title: str
    content: str


class WorkbookDocument(BaseModel):
    """Incremental workbook/handbook state."""

    workbook_title: Optional[str] = None
    company_name: Optional[str] = None
    industry: Optional[str] = None
    objective: Optional[str] = None
    sections: Optional[list[WorkbookSection]] = None
    images: Optional[list[str]] = None  # S3/CDN URLs for presentation images


class CreateThreadRequest(BaseModel):
    title: Optional[str] = None
    initial_message: Optional[str] = None


class CreateThreadResponse(BaseModel):
    id: UUID
    title: str
    status: str
    current_state: dict
    version: int
    is_pinned: bool = False
    created_at: datetime
    assistant_reply: Optional[str] = None
    pdf_url: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class MWMessageOut(BaseModel):
    id: UUID
    thread_id: UUID
    role: str
    content: str
    version_created: Optional[int] = None
    created_at: datetime


class TokenUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated: bool = False
    model: Optional[str] = None


class SendMessageResponse(BaseModel):
    user_message: MWMessageOut
    assistant_message: MWMessageOut
    current_state: dict
    version: int
    pdf_url: Optional[str] = None
    token_usage: Optional[TokenUsage] = None


class ThreadListItem(BaseModel):
    id: UUID
    title: str
    status: str
    version: int
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime


class ElementListItem(BaseModel):
    id: UUID
    thread_id: UUID
    element_type: str
    title: str
    status: str
    version: int
    linked_offer_letter_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class ThreadDetailResponse(BaseModel):
    id: UUID
    title: str
    status: str
    current_state: dict
    version: int
    is_pinned: bool = False
    linked_offer_letter_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    messages: list[MWMessageOut]


class DocumentVersionResponse(BaseModel):
    id: UUID
    thread_id: UUID
    version: int
    state_json: dict
    diff_summary: Optional[str] = None
    created_at: datetime


class RevertRequest(BaseModel):
    version: int


class FinalizeResponse(BaseModel):
    thread_id: UUID
    status: str
    version: int
    pdf_url: Optional[str] = None
    linked_offer_letter_id: Optional[UUID] = None


class SaveDraftResponse(BaseModel):
    thread_id: UUID
    linked_offer_letter_id: UUID
    offer_status: str
    saved_at: datetime


class UpdateTitleRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class PinThreadRequest(BaseModel):
    is_pinned: bool = True


class UsageTotals(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    operation_count: int = 0
    estimated_operations: int = 0


class UsageByModel(BaseModel):
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    operation_count: int = 0
    estimated_operations: int = 0
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None


class UsageSummaryResponse(BaseModel):
    period_days: int
    generated_at: datetime
    totals: UsageTotals
    by_model: list[UsageByModel]


class SendReviewRequestsRequest(BaseModel):
    recipient_emails: list[str] = Field(default_factory=list, max_length=100)
    custom_message: Optional[str] = Field(default=None, max_length=2000)


class ReviewRequestStatus(BaseModel):
    email: str
    status: Literal["pending", "sent", "failed", "submitted"]
    sent_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    last_error: Optional[str] = None


class SendReviewRequestsResponse(BaseModel):
    thread_id: UUID
    expected_responses: int
    received_responses: int
    pending_responses: int
    sent_count: int
    failed_count: int
    recipients: list[ReviewRequestStatus]


class PublicReviewRequestResponse(BaseModel):
    token: str
    review_title: str
    recipient_email: str
    status: Literal["pending", "sent", "failed", "submitted"]
    submitted_at: Optional[datetime] = None


class PublicReviewSubmitRequest(BaseModel):
    feedback: str = Field(..., min_length=1, max_length=8000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)


class PublicReviewSubmitResponse(BaseModel):
    status: Literal["submitted"]
    submitted_at: datetime


class SendHandbookSignaturesRequest(BaseModel):
    handbook_id: UUID
    employee_ids: list[UUID] = Field(default_factory=list)


class SendHandbookSignaturesResponse(BaseModel):
    handbook_id: UUID
    handbook_version: int
    assigned_count: int
    skipped_existing_count: int
    distributed_at: datetime


class GeneratePresentationResponse(BaseModel):
    thread_id: UUID
    version: int
    current_state: dict
    slide_count: int
    generated_at: datetime
