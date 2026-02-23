from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

import re
from pydantic import BaseModel, Field, field_validator, model_validator


class OfferLetterStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OfferLetterBase(BaseModel):
    candidate_name: str = Field(..., min_length=1, max_length=255)
    position_title: str = Field(..., min_length=1, max_length=255)
    company_name: str
    company_id: Optional[UUID] = None
    salary: Optional[str] = None
    bonus: Optional[str] = None
    stock_options: Optional[str] = None
    start_date: Optional[datetime] = None
    employment_type: Optional[str] = "Full-Time Exempt"
    location: Optional[str] = "Remote"
    benefits: Optional[str] = None  # Legacy free-text field
    manager_name: Optional[str] = None
    manager_title: Optional[str] = None
    expiration_date: Optional[datetime] = None
    # Structured benefits
    benefits_medical: bool = False
    benefits_medical_coverage: Optional[int] = None
    benefits_medical_waiting_days: int = 0
    benefits_dental: bool = False
    benefits_vision: bool = False
    benefits_401k: bool = False
    benefits_401k_match: Optional[str] = None
    benefits_wellness: Optional[str] = None
    benefits_pto_vacation: bool = False
    benefits_pto_sick: bool = False
    benefits_holidays: bool = False
    benefits_other: Optional[str] = None
    # Contingencies
    contingency_background_check: bool = False
    contingency_credit_check: bool = False
    contingency_drug_screening: bool = False
    # Company logo
    company_logo_url: Optional[str] = None
    # Salary range negotiation
    salary_range_min: Optional[float] = Field(default=None, ge=0)
    salary_range_max: Optional[float] = Field(default=None, ge=0)
    candidate_email: Optional[str] = None
    max_negotiation_rounds: int = Field(default=3, ge=1, le=10)


class OfferLetterCreate(OfferLetterBase):
    pass


class OfferLetterUpdate(BaseModel):
    candidate_name: Optional[str] = Field(None, min_length=1, max_length=255)
    position_title: Optional[str] = Field(None, min_length=1, max_length=255)
    company_name: Optional[str] = None
    status: Optional[OfferLetterStatus] = None
    salary: Optional[str] = None
    bonus: Optional[str] = None
    stock_options: Optional[str] = None
    start_date: Optional[datetime] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    benefits: Optional[str] = None
    manager_name: Optional[str] = None
    manager_title: Optional[str] = None
    expiration_date: Optional[datetime] = None
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
    # Salary range negotiation
    salary_range_min: Optional[float] = Field(default=None, ge=0)
    salary_range_max: Optional[float] = Field(default=None, ge=0)
    candidate_email: Optional[str] = None
    max_negotiation_rounds: Optional[int] = Field(default=None, ge=1, le=10)


class OfferGuidanceRequest(BaseModel):
    role_title: str = Field(..., min_length=2, max_length=120)
    city: str = Field(..., min_length=2, max_length=120)
    state: Optional[str] = Field(default=None, min_length=2, max_length=80)
    years_experience: int = Field(..., ge=0, le=40)
    employment_type: Optional[str] = Field(default=None, max_length=80)


class OfferGuidanceResponse(BaseModel):
    role_family: str
    normalized_city: str
    normalized_state: Optional[str] = None
    salary_low: int
    salary_mid: int
    salary_high: int
    bonus_target_pct_low: int
    bonus_target_pct_high: int
    equity_guidance: str
    confidence: float
    rationale: list[str]


class OfferLetter(OfferLetterBase):
    id: UUID
    status: OfferLetterStatus
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime] = None
    matched_salary: Optional[float] = None
    range_match_status: Optional[str] = None
    negotiation_round: int = 1


class CandidateOfferView(BaseModel):
    id: UUID
    position_title: str
    company_name: str
    company_logo_url: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    salary_range_min: float
    salary_range_max: float
    benefits_medical: bool = False
    benefits_dental: bool = False
    benefits_vision: bool = False
    benefits_401k: bool = False
    benefits_401k_match: Optional[str] = None
    benefits_pto_vacation: bool = False
    benefits_pto_sick: bool = False
    benefits_holidays: bool = False
    benefits_other: Optional[str] = None
    start_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    range_match_status: str
    negotiation_round: int
    max_negotiation_rounds: int
    matched_salary: Optional[float] = None


class SendRangeRequest(BaseModel):
    candidate_email: str
    salary_range_min: float = Field(..., gt=0)
    salary_range_max: float = Field(..., gt=0)

    @field_validator("candidate_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Invalid email address")
        return v

    @model_validator(mode="after")
    def validate_range(self) -> "SendRangeRequest":
        if self.salary_range_min > self.salary_range_max:
            raise ValueError("salary_range_min must be ≤ salary_range_max")
        return self


class CandidateRangeSubmit(BaseModel):
    range_min: float = Field(..., ge=0)
    range_max: float = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "CandidateRangeSubmit":
        if self.range_min > self.range_max:
            raise ValueError("range_min must be ≤ range_max")
        return self


class RangeNegotiateResult(BaseModel):
    result: str  # matched | no_match_low | no_match_high
    matched_salary: Optional[float] = None


class ReNegotiateRequest(BaseModel):
    salary_range_min: Optional[float] = None
    salary_range_max: Optional[float] = None
