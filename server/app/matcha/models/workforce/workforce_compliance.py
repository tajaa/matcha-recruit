"""Pydantic models for the Workforce Compliance bundle (business-first EPL trackers)."""

from datetime import date, datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# --- AI hiring-tool audit register ---

class HiringAiAuditCreate(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=255)
    vendor: Optional[str] = None
    purpose: Optional[str] = None
    last_audit_date: Optional[date] = None
    cadence_days: int = Field(default=365, ge=1, le=3650)
    notes: Optional[str] = None


class HiringAiAuditUpdate(BaseModel):
    tool_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    vendor: Optional[str] = None
    purpose: Optional[str] = None
    last_audit_date: Optional[date] = None
    cadence_days: Optional[int] = Field(default=None, ge=1, le=3650)
    notes: Optional[str] = None


class HiringAiAuditResponse(BaseModel):
    id: UUID
    company_id: UUID
    tool_name: str
    vendor: Optional[str] = None
    purpose: Optional[str] = None
    last_audit_date: Optional[date] = None
    cadence_days: int
    next_due_date: Optional[date] = None
    is_overdue: bool
    notes: Optional[str] = None
    created_at: datetime


# --- Biometric / BIPA consent inventory ---

CollectionType = Literal["fingerprint", "face", "iris", "voice", "hand_geometry", "other"]
ConsentMethod = Literal["written", "digital", "verbal", "other"]


class BiometricPointCreate(BaseModel):
    collection_type: CollectionType
    location_id: Optional[UUID] = None
    purpose: Optional[str] = None
    consent_obtained: bool = False
    consent_obtained_date: Optional[date] = None
    consent_method: Optional[ConsentMethod] = None
    retention_policy: Optional[str] = None
    notes: Optional[str] = None


class BiometricPointUpdate(BaseModel):
    collection_type: Optional[CollectionType] = None
    location_id: Optional[UUID] = None
    purpose: Optional[str] = None
    consent_obtained: Optional[bool] = None
    consent_obtained_date: Optional[date] = None
    consent_method: Optional[ConsentMethod] = None
    retention_policy: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class BiometricPointResponse(BaseModel):
    id: UUID
    company_id: UUID
    location_id: Optional[UUID] = None
    collection_type: str
    purpose: Optional[str] = None
    consent_obtained: bool
    consent_obtained_date: Optional[date] = None
    consent_method: Optional[str] = None
    retention_policy: Optional[str] = None
    is_active: bool
    notes: Optional[str] = None
    created_at: datetime


# --- Pay transparency per-state status ---

class PayTransparencyStateRow(BaseModel):
    state: str
    required: bool
    status: str          # compliant | action_needed | na
    postings_include_ranges: bool
    note: Optional[str] = None
    updated_at: Optional[datetime] = None


class PayTransparencyUpdate(BaseModel):
    status: Literal["compliant", "action_needed", "na"]
    postings_include_ranges: bool = False
    note: Optional[str] = None


# --- Pay-equity study register ---

class PayEquityReviewCreate(BaseModel):
    review_date: Optional[date] = None
    scope: Optional[str] = None
    methodology: Optional[str] = None
    gap_pct: Optional[float] = Field(default=None, ge=0, le=100)
    remediation: Optional[str] = None
    cadence_days: int = Field(default=365, ge=1)
    notes: Optional[str] = None


class PayEquityReviewUpdate(BaseModel):
    review_date: Optional[date] = None
    scope: Optional[str] = None
    methodology: Optional[str] = None
    gap_pct: Optional[float] = Field(default=None, ge=0, le=100)
    remediation: Optional[str] = None
    cadence_days: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None
