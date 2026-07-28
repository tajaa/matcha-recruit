"""Resident-care risk asset models — safety programs + MVR reviews."""

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

ProgramType = Literal[
    "fall_prevention", "infection_control", "abuse_prevention",
    "emergency_prep", "medication_safety", "other",
]
ProgramStatus = Literal["active", "inactive"]
ReviewType = Literal["hire", "annual"]
MvrStatus = Literal["clear", "flagged", "pending"]


class SafetyProgramCreate(BaseModel):
    program_type: ProgramType
    name: str = Field(..., min_length=1, max_length=255)
    status: ProgramStatus = "active"
    last_reviewed_date: Optional[date] = None
    owner: Optional[str] = None
    notes: Optional[str] = None


class SafetyProgramUpdate(BaseModel):
    program_type: Optional[ProgramType] = None
    name: Optional[str] = None
    status: Optional[ProgramStatus] = None
    last_reviewed_date: Optional[date] = None
    owner: Optional[str] = None
    notes: Optional[str] = None


class MvrReviewCreate(BaseModel):
    driver_name: str = Field(..., min_length=1, max_length=255)
    employee_id: Optional[UUID] = None
    review_type: ReviewType = "annual"
    review_date: Optional[date] = None
    status: MvrStatus = "pending"
    next_due_date: Optional[date] = None
    notes: Optional[str] = None


class MvrReviewUpdate(BaseModel):
    driver_name: Optional[str] = None
    review_type: Optional[ReviewType] = None
    review_date: Optional[date] = None
    status: Optional[MvrStatus] = None
    next_due_date: Optional[date] = None
    notes: Optional[str] = None
