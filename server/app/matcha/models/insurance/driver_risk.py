"""Driver-risk / MVR request models (gap-analysis #15)."""

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

ReviewType = Literal["hire", "annual", "post_incident", "periodic"]
MvrStatus = Literal["clear", "flagged", "pending"]
LicenseStatus = Literal["valid", "suspended", "expired", "unknown"]


class DriverReviewCreate(BaseModel):
    driver_name: str = Field(..., min_length=1, max_length=255)
    employee_id: Optional[UUID] = None
    review_type: ReviewType = "annual"
    review_date: Optional[date] = None
    status: MvrStatus = "pending"
    next_due_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=2000)
    violation_count: int = Field(0, ge=0)
    accident_count: int = Field(0, ge=0)
    major_violation: bool = False
    license_status: LicenseStatus = "valid"


class DriverReviewUpdate(BaseModel):
    driver_name: Optional[str] = Field(None, min_length=1, max_length=255)
    review_type: Optional[ReviewType] = None
    review_date: Optional[date] = None
    status: Optional[MvrStatus] = None
    next_due_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=2000)
    violation_count: Optional[int] = Field(None, ge=0)
    accident_count: Optional[int] = Field(None, ge=0)
    major_violation: Optional[bool] = None
    license_status: Optional[LicenseStatus] = None
