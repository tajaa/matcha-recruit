from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel


# Deal types
CompensationType = Literal["fixed", "per_deliverable", "revenue_share", "product_only", "negotiable"]
DealStatus = Literal["draft", "open", "closed", "filled", "cancelled"]
DealVisibility = Literal["public", "invite_only", "private"]
ApplicationStatus = Literal["pending", "under_review", "shortlisted", "accepted", "rejected", "withdrawn"]
ContractStatus = Literal["pending", "active", "completed", "cancelled", "disputed"]
PaymentStatus = Literal["pending", "invoiced", "paid", "overdue", "cancelled"]


# Brand Deal models
class BrandDealCreate(BaseModel):
    title: str
    brand_name: str
    description: str
    requirements: Optional[dict] = None
    deliverables: Optional[list[dict]] = None
    compensation_type: CompensationType
    compensation_min: Optional[Decimal] = None
    compensation_max: Optional[Decimal] = None
    compensation_currency: str = "USD"
    compensation_details: Optional[str] = None
    niches: Optional[list[str]] = None
    min_followers: Optional[int] = None
    max_followers: Optional[int] = None
    preferred_platforms: Optional[list[str]] = None
    audience_requirements: Optional[dict] = None
    timeline_start: Optional[date] = None
    timeline_end: Optional[date] = None
    application_deadline: Optional[date] = None
    visibility: DealVisibility = "public"


class BrandDealUpdate(BaseModel):
    title: Optional[str] = None
    brand_name: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[dict] = None
    deliverables: Optional[list[dict]] = None
    compensation_type: Optional[CompensationType] = None
    compensation_min: Optional[Decimal] = None
    compensation_max: Optional[Decimal] = None
    compensation_currency: Optional[str] = None
    compensation_details: Optional[str] = None
    niches: Optional[list[str]] = None
    min_followers: Optional[int] = None
    max_followers: Optional[int] = None
    preferred_platforms: Optional[list[str]] = None
    audience_requirements: Optional[dict] = None
    timeline_start: Optional[date] = None
    timeline_end: Optional[date] = None
    application_deadline: Optional[date] = None
    status: Optional[DealStatus] = None
    visibility: Optional[DealVisibility] = None


class BrandDealResponse(BaseModel):
    id: UUID
    agency_id: UUID
    agency_name: Optional[str] = None
    title: str
    brand_name: str
    description: str
    requirements: dict
    deliverables: list[dict]
    compensation_type: CompensationType
    compensation_min: Optional[Decimal]
    compensation_max: Optional[Decimal]
    compensation_currency: str
    compensation_details: Optional[str]
    niches: list[str]
    min_followers: Optional[int]
    max_followers: Optional[int]
    preferred_platforms: list[str]
    audience_requirements: dict
    timeline_start: Optional[date]
    timeline_end: Optional[date]
    application_deadline: Optional[date]
    status: DealStatus
    visibility: DealVisibility
    applications_count: int
    created_at: datetime
    updated_at: datetime


class BrandDealPublicResponse(BaseModel):
    """Public deal listing for creator marketplace."""
    id: UUID
    agency_name: str
    agency_verified: bool
    title: str
    brand_name: str
    description: str
    deliverables: list[dict]
    compensation_type: CompensationType
    compensation_min: Optional[Decimal]
    compensation_max: Optional[Decimal]
    compensation_currency: str
    niches: list[str]
    min_followers: Optional[int]
    max_followers: Optional[int]
    preferred_platforms: list[str]
    timeline_start: Optional[date]
    timeline_end: Optional[date]
    application_deadline: Optional[date]
    created_at: datetime


# Application models
class DealApplicationCreate(BaseModel):
    pitch: str
    proposed_rate: Optional[Decimal] = None
    proposed_currency: str = "USD"
    proposed_deliverables: Optional[list[dict]] = None
    portfolio_links: Optional[list[str]] = None
    availability_notes: Optional[str] = None


class DealApplicationUpdate(BaseModel):
    pitch: Optional[str] = None
    proposed_rate: Optional[Decimal] = None
    proposed_deliverables: Optional[list[dict]] = None
    portfolio_links: Optional[list[str]] = None
    availability_notes: Optional[str] = None


class DealApplicationResponse(BaseModel):
    id: UUID
    deal_id: UUID
    deal_title: Optional[str] = None
    creator_id: UUID
    creator_name: Optional[str] = None
    pitch: str
    proposed_rate: Optional[Decimal]
    proposed_currency: str
    proposed_deliverables: list[dict]
    portfolio_links: list[str]
    availability_notes: Optional[str]
    status: ApplicationStatus
    agency_notes: Optional[str]
    match_score: Optional[float]
    created_at: datetime
    updated_at: datetime


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus
    agency_notes: Optional[str] = None


# Contract models
class ContractCreate(BaseModel):
    agreed_rate: Decimal
    agreed_currency: str = "USD"
    agreed_deliverables: list[dict]
    terms: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ContractResponse(BaseModel):
    id: UUID
    deal_id: UUID
    deal_title: Optional[str] = None
    application_id: UUID
    creator_id: UUID
    creator_name: Optional[str] = None
    agency_id: UUID
    agency_name: Optional[str] = None
    agreed_rate: Decimal
    agreed_currency: str
    agreed_deliverables: list[dict]
    terms: Optional[str]
    contract_document_url: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    status: ContractStatus
    total_paid: Decimal
    created_at: datetime
    updated_at: datetime


class ContractStatusUpdate(BaseModel):
    status: ContractStatus


# Payment models
class PaymentCreate(BaseModel):
    amount: Decimal
    currency: str = "USD"
    milestone_name: Optional[str] = None
    due_date: Optional[date] = None


class PaymentUpdate(BaseModel):
    status: Optional[PaymentStatus] = None
    paid_date: Optional[date] = None
    payment_method: Optional[str] = None
    transaction_reference: Optional[str] = None
    notes: Optional[str] = None


class PaymentResponse(BaseModel):
    id: UUID
    contract_id: UUID
    amount: Decimal
    currency: str
    milestone_name: Optional[str]
    due_date: Optional[date]
    paid_date: Optional[date]
    status: PaymentStatus
    payment_method: Optional[str]
    transaction_reference: Optional[str]
    notes: Optional[str]
    created_at: datetime


# Match models
class CreatorDealMatchResponse(BaseModel):
    id: UUID
    deal_id: UUID
    creator_id: UUID
    creator_name: Optional[str] = None
    overall_score: float
    niche_score: Optional[float]
    audience_score: Optional[float]
    engagement_score: Optional[float]
    budget_fit_score: Optional[float]
    match_reasoning: Optional[str]
    breakdown: dict
    created_at: datetime
