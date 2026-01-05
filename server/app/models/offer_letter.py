from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class OfferLetterBase(BaseModel):
    candidate_name: str
    position_title: str
    company_name: str
    salary: Optional[str] = None
    bonus: Optional[str] = None
    stock_options: Optional[str] = None
    start_date: Optional[datetime] = None
    employment_type: Optional[str] = "Full-time"
    location: Optional[str] = "Remote"
    benefits: Optional[str] = None
    manager_name: Optional[str] = None
    manager_title: Optional[str] = None
    expiration_date: Optional[datetime] = None


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


class OfferLetter(OfferLetterBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime] = None
