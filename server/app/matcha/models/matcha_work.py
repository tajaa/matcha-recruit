from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


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


class CreateThreadRequest(BaseModel):
    title: Optional[str] = None
    initial_message: Optional[str] = None


class CreateThreadResponse(BaseModel):
    id: UUID
    title: str
    status: str
    current_state: dict
    version: int
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


class SendMessageResponse(BaseModel):
    user_message: MWMessageOut
    assistant_message: MWMessageOut
    current_state: dict
    version: int
    pdf_url: Optional[str] = None


class ThreadListItem(BaseModel):
    id: UUID
    title: str
    task_type: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ThreadDetailResponse(BaseModel):
    id: UUID
    title: str
    task_type: str
    status: str
    current_state: dict
    version: int
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


class UpdateTitleRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
