from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel


# Platform types
Platform = Literal["youtube", "patreon", "tiktok", "instagram", "twitch", "twitter", "spotify"]
SyncStatus = Literal["pending", "syncing", "synced", "failed"]

# Revenue categories
RevenueCategory = Literal[
    "adsense", "sponsorship", "affiliate", "merch",
    "subscription", "tips", "licensing", "services", "other"
]

# Expense categories
ExpenseCategory = Literal[
    "equipment", "software", "travel", "marketing",
    "contractors", "office", "education", "legal", "other"
]


# Creator Profile models
class CreatorCreate(BaseModel):
    display_name: str
    bio: Optional[str] = None
    niches: Optional[list[str]] = None
    social_handles: Optional[dict] = None
    is_public: bool = True


class CreatorUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    profile_image_url: Optional[str] = None
    niches: Optional[list[str]] = None
    social_handles: Optional[dict] = None
    audience_demographics: Optional[dict] = None
    is_public: Optional[bool] = None


class CreatorResponse(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str
    bio: Optional[str]
    profile_image_url: Optional[str]
    niches: list[str]
    social_handles: dict
    audience_demographics: dict
    metrics: dict
    is_verified: bool
    is_public: bool
    created_at: datetime
    updated_at: datetime


class CreatorPublicResponse(BaseModel):
    """Public creator profile (for marketplace discovery)"""
    id: UUID
    display_name: str
    bio: Optional[str]
    profile_image_url: Optional[str]
    niches: list[str]
    audience_demographics: dict
    metrics: dict
    is_verified: bool


# Platform connection models
class PlatformConnectionResponse(BaseModel):
    id: UUID
    creator_id: UUID
    platform: Platform
    platform_username: Optional[str]
    last_synced_at: Optional[datetime]
    sync_status: SyncStatus
    sync_error: Optional[str]
    platform_data: dict
    created_at: datetime


class PlatformConnectRequest(BaseModel):
    platform: Platform
    authorization_code: str
    redirect_uri: str


# Revenue stream models
class RevenueStreamCreate(BaseModel):
    name: str
    category: RevenueCategory
    platform: Optional[str] = None
    description: Optional[str] = None
    tax_category: Optional[str] = None


class RevenueStreamUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[RevenueCategory] = None
    platform: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    tax_category: Optional[str] = None


class RevenueStreamResponse(BaseModel):
    id: UUID
    creator_id: UUID
    name: str
    category: RevenueCategory
    platform: Optional[str]
    description: Optional[str]
    is_active: bool
    tax_category: Optional[str]
    created_at: datetime


# Revenue entry models
class RevenueEntryCreate(BaseModel):
    stream_id: Optional[UUID] = None
    amount: Decimal
    currency: str = "USD"
    date: date
    description: Optional[str] = None
    source: Optional[str] = None
    is_recurring: bool = False
    tax_category: Optional[str] = None


class RevenueEntryUpdate(BaseModel):
    stream_id: Optional[UUID] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    date: Optional[date] = None
    description: Optional[str] = None
    source: Optional[str] = None
    is_recurring: Optional[bool] = None
    tax_category: Optional[str] = None


class RevenueEntryResponse(BaseModel):
    id: UUID
    creator_id: UUID
    stream_id: Optional[UUID]
    stream_name: Optional[str] = None
    amount: Decimal
    currency: str
    date: date
    description: Optional[str]
    source: Optional[str]
    is_recurring: bool
    tax_category: Optional[str]
    created_at: datetime


# Expense models
class ExpenseCreate(BaseModel):
    amount: Decimal
    currency: str = "USD"
    date: date
    category: ExpenseCategory
    description: str
    vendor: Optional[str] = None
    is_deductible: bool = True
    tax_category: Optional[str] = None


class ExpenseUpdate(BaseModel):
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    date: Optional[date] = None
    category: Optional[ExpenseCategory] = None
    description: Optional[str] = None
    vendor: Optional[str] = None
    receipt_url: Optional[str] = None
    is_deductible: Optional[bool] = None
    tax_category: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: UUID
    creator_id: UUID
    amount: Decimal
    currency: str
    date: date
    category: ExpenseCategory
    description: str
    vendor: Optional[str]
    receipt_url: Optional[str]
    is_deductible: bool
    tax_category: Optional[str]
    created_at: datetime


# Dashboard/analytics models
class RevenueSummary(BaseModel):
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal
    revenue_by_category: dict[str, Decimal]
    revenue_by_stream: dict[str, Decimal]
    expenses_by_category: dict[str, Decimal]
    period_start: date
    period_end: date


class MonthlyRevenue(BaseModel):
    month: str  # YYYY-MM format
    revenue: Decimal
    expenses: Decimal
    net: Decimal


class RevenueOverview(BaseModel):
    current_month: RevenueSummary
    previous_month: RevenueSummary
    year_to_date: RevenueSummary
    monthly_trend: list[MonthlyRevenue]
