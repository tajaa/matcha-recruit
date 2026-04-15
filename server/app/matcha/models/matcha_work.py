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


class HandbookProfileFlags(BaseModel):
    remote_workers: Optional[bool] = None
    minors: Optional[bool] = None
    tipped_employees: Optional[bool] = None
    tip_pooling: Optional[bool] = None
    union_employees: Optional[bool] = None
    federal_contracts: Optional[bool] = None
    group_health_insurance: Optional[bool] = None
    background_checks: Optional[bool] = None
    hourly_employees: Optional[bool] = None
    salaried_employees: Optional[bool] = None
    commissioned_employees: Optional[bool] = None


class HandbookCustomSection(BaseModel):
    title: str
    content: str


class HandbookSectionPreview(BaseModel):
    section_key: str
    title: str
    content: str  # truncated to 500 chars
    section_type: Optional[str] = None


class HandbookRedFlag(BaseModel):
    id: str
    severity: Literal["high", "medium", "low"] = "medium"
    jurisdiction: str
    section_title: str
    summary: str
    why_it_matters: str
    recommended_action: str


class HandbookDocument(BaseModel):
    """Incremental handbook state — builds turn by turn via conversation."""

    handbook_title: Optional[str] = None
    handbook_source_type: Optional[Literal["template", "upload"]] = None
    handbook_upload_status: Optional[
        Literal["idle", "uploading", "analyzing", "reviewed", "error", "blocked"]
    ] = None
    handbook_uploaded_file_url: Optional[str] = None
    handbook_uploaded_filename: Optional[str] = None
    handbook_mode: Optional[str] = None  # single_state, multi_state
    handbook_industry: Optional[str] = None
    handbook_sub_industry: Optional[str] = None
    handbook_states: Optional[list[str]] = None
    handbook_legal_name: Optional[str] = None
    handbook_dba: Optional[str] = None
    handbook_ceo: Optional[str] = None
    handbook_headcount: Optional[int] = None
    handbook_profile: Optional[HandbookProfileFlags] = None
    handbook_custom_sections: Optional[list[HandbookCustomSection]] = None
    handbook_guided_answers: Optional[dict[str, str]] = None
    handbook_status: Optional[str] = None
    handbook_id: Optional[str] = None
    handbook_sections: Optional[list[HandbookSectionPreview]] = None
    handbook_error: Optional[str] = None
    handbook_blocking_error: Optional[str] = None
    handbook_review_locations: Optional[list[str]] = None
    handbook_red_flags: Optional[list[HandbookRedFlag]] = None
    handbook_analysis_generated_at: Optional[str] = None
    handbook_strength_score: Optional[int] = None
    handbook_strength_label: Optional[str] = None
    handbook_analysis_progress: Optional[float] = None
    handbook_total_red_flag_count: Optional[int] = None


class PresentationSlide(BaseModel):
    title: str
    bullets: Optional[list[str]] = None
    speaker_notes: Optional[str] = None


class PresentationDocument(BaseModel):
    """Standalone presentation/report state — AI generates slides directly."""

    presentation_title: Optional[str] = None
    subtitle: Optional[str] = None
    theme: Optional[str] = None  # professional, minimal, bold
    slides: Optional[list[PresentationSlide]] = None
    cover_image_url: Optional[str] = None
    generated_at: Optional[str] = None


class ResumeCandidate(BaseModel):
    """Structured candidate data extracted from a resume."""

    id: str
    filename: str
    resume_url: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    current_title: Optional[str] = None
    experience_years: Optional[float] = None
    skills: Optional[list[str]] = None
    education: Optional[str] = None
    certifications: Optional[list[str]] = None
    summary: Optional[str] = None
    strengths: Optional[list[str]] = None
    flags: Optional[list[str]] = None
    status: str = "pending"


class ResumeBatchDocument(BaseModel):
    """Resume batch state — candidates accumulated via uploads."""

    batch_title: Optional[str] = None
    batch_status: Optional[str] = None  # uploading, analyzing, ready
    candidates: Optional[list[ResumeCandidate]] = None
    total_count: Optional[int] = None
    analyzed_count: Optional[int] = None


class InventoryItem(BaseModel):
    """Structured line item extracted from a vendor invoice or inventory sheet."""

    id: str
    filename: str
    product_name: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None  # protein, produce, dairy, dry_goods, beverages, supplies, equipment, other
    quantity: Optional[float] = None
    unit: Optional[str] = None  # case, lb, each, gal, oz, bag, box, doz, pack
    unit_cost: Optional[float] = None
    total_cost: Optional[float] = None
    vendor: Optional[str] = None
    par_level: Optional[float] = None
    status: str = "extracted"  # extracted, verified, flagged


class InventoryDocument(BaseModel):
    """Inventory batch state — line items accumulated via invoice/spreadsheet uploads."""

    inventory_title: Optional[str] = None
    inventory_status: Optional[str] = None  # uploading, analyzing, ready
    inventory_items: Optional[list[InventoryItem]] = None
    inventory_total_count: Optional[int] = None
    inventory_total_cost: Optional[float] = None
    inventory_vendors: Optional[list[str]] = None


class ProjectSection(BaseModel):
    """A section within a project document."""

    id: str
    title: Optional[str] = None
    content: str  # markdown
    source_message_id: Optional[str] = None


class ProjectDocument(BaseModel):
    """Project document state — user-editable sections built from chat content."""

    project_title: Optional[str] = None
    project_sections: Optional[list[ProjectSection]] = None
    project_status: Optional[str] = None  # drafting, finalized


class PolicyDocument(BaseModel):
    """Incremental policy draft state — builds turn by turn via conversation."""

    policy_title: Optional[str] = None
    policy_type: Optional[str] = None  # pto_sick_leave, meal_rest_breaks, overtime, etc.
    policy_locations: Optional[list[str]] = None  # location IDs from compliance
    policy_location_names: Optional[list[str]] = None  # display names (e.g. "San Francisco, CA")
    policy_additional_context: Optional[str] = None
    policy_content: Optional[str] = None  # the generated policy text (markdown)
    policy_status: Optional[str] = None  # collecting, generating, created
    policy_id: Optional[str] = None  # linked policy ID after save


class CreateThreadRequest(BaseModel):
    title: Optional[str] = None
    initial_message: Optional[str] = None


class CreateThreadResponse(BaseModel):
    id: UUID
    title: str
    status: str
    current_state: dict
    version: int
    task_type: Optional[str] = None
    is_pinned: bool = False
    node_mode: bool = False
    compliance_mode: bool = False
    payer_mode: bool = False
    created_at: datetime
    assistant_reply: Optional[str] = None
    pdf_url: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    slide_index: Optional[int] = Field(None, ge=0, description="0-based index of slide to focus edits on")
    model: Optional[str] = Field(None, description="Model override (e.g. gemini-3.1-flash-lite-preview, gemini-3-flash-preview, gemini-3.1-pro-preview)")


class SendInterviewsRequest(BaseModel):
    candidate_ids: list[str]
    position_title: Optional[str] = None
    custom_message: Optional[str] = None


class RejectCandidateRequest(BaseModel):
    rejection_reason: Optional[str] = None  # internal note saved on candidate
    custom_message: Optional[str] = None     # appears in rejection email body
    send_email: bool = True                  # False = silent dismiss semantics


class MWMessageOut(BaseModel):
    id: UUID
    thread_id: UUID
    role: str
    content: str
    version_created: Optional[int] = None
    metadata: Optional[dict] = None
    created_at: datetime


class TokenUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated: bool = False
    model: Optional[str] = None
    cost_dollars: Optional[float] = None


class SendMessageResponse(BaseModel):
    user_message: MWMessageOut
    assistant_message: MWMessageOut
    current_state: dict
    version: int
    task_type: Optional[str] = None
    pdf_url: Optional[str] = None
    token_usage: Optional[TokenUsage] = None


class ThreadListItem(BaseModel):
    id: UUID
    title: str
    status: str
    version: int
    task_type: Optional[str] = None
    is_pinned: bool = False
    node_mode: bool = False
    compliance_mode: bool = False
    payer_mode: bool = False
    collaborator_count: int = 0
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
    task_type: Optional[str] = None
    is_pinned: bool = False
    node_mode: bool = False
    compliance_mode: bool = False
    payer_mode: bool = False
    linked_offer_letter_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    messages: list[MWMessageOut]
    collaborators: list[dict] = []


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


class NodeModeRequest(BaseModel):
    node_mode: bool = True


class ComplianceModeRequest(BaseModel):
    compliance_mode: bool = True


class PayerModeRequest(BaseModel):
    payer_mode: bool = True


class UsageTotals(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    operation_count: int = 0
    estimated_operations: int = 0
    total_cost_dollars: float = 0


class UsageByModel(BaseModel):
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    operation_count: int = 0
    estimated_operations: int = 0
    total_cost_dollars: float = 0
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
