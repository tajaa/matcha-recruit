from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class OfferLetterBase(BaseModel):
    candidate_name: str
    position_title: str
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


class OfferLetterCreate(OfferLetterBase):
    pass


class OfferLetterUpdate(BaseModel):
    candidate_name: Optional[str] = None
    position_title: Optional[str] = None
    company_name: Optional[str] = None
    status: Optional[str] = None
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


class OfferLetter(OfferLetterBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime] = None
