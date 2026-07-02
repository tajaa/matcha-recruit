"""Pydantic request/response shapes for Tell-Us."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

AccountType = Literal["consumer", "brand"]
ReportCategory = Literal["service", "cleanliness", "facilities", "safety", "compliment", "other"]
Sentiment = Literal["positive", "neutral", "negative"]
ReportStatus = Literal["new", "reviewing", "resolved", "archived"]
MediaType = Literal["photo", "video"]
RedemptionType = Literal["code", "qr", "manual"]
RedemptionStatus = Literal["pending", "issued", "redeemed", "expired", "cancelled"]


# ── Auth ────────────────────────────────────────────────────────────────────

class TellusSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: Optional[str] = Field(default=None, max_length=255)
    account_type: AccountType = "consumer"
    # Brand-only: name of the brand to create on signup.
    brand_name: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)


class TellusLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class TellusRefreshRequest(BaseModel):
    refresh_token: str


class TellusVerifyRequest(BaseModel):
    token: str


class TellusResendRequest(BaseModel):
    email: EmailStr


class TellusAccount(BaseModel):
    """The authenticated Tell-Us identity (returned by require_tellus_account)."""
    id: UUID
    email: str
    display_name: Optional[str] = None
    account_type: str = "consumer"
    status: str = "active"
    city: Optional[str] = None
    state: Optional[str] = None
    leaderboard_opt_in: bool = True
    # Populated for brand accounts (the brand they own).
    brand_id: Optional[UUID] = None


class TellusTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    account: TellusAccount


class TellusSignupResponse(BaseModel):
    verification_required: bool
    email: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    account: Optional[TellusAccount] = None


class TellusLocationUpdate(BaseModel):
    """Consumer sets/updates their city — geocoded to power the marketplace."""
    city: str = Field(min_length=1, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    zipcode: Optional[str] = Field(default=None, max_length=20)


class TellusProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=255)
    leaderboard_opt_in: Optional[bool] = None


# ── Brands & stores ───────────────────────────────────────────────────────────

class TellusBrand(BaseModel):
    id: UUID
    owner_account_id: UUID
    name: str
    logo_url: Optional[str] = None
    created_at: datetime


class TellusBrandUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    logo_url: Optional[str] = Field(default=None, max_length=2000)


class TellusStoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    zipcode: Optional[str] = Field(default=None, max_length=20)


class TellusStoreUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    zipcode: Optional[str] = Field(default=None, max_length=20)


class TellusStore(BaseModel):
    id: UUID
    brand_id: UUID
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    created_at: datetime


# ── Links (QR) ────────────────────────────────────────────────────────────────

class TellusLinkCreate(BaseModel):
    store_id: Optional[UUID] = None
    label: Optional[str] = Field(default=None, max_length=200)
    max_uses: Optional[int] = Field(default=None, ge=1)
    expires_at: Optional[datetime] = None


class TellusLink(BaseModel):
    id: UUID
    brand_id: UUID
    store_id: Optional[UUID] = None
    token: str
    label: Optional[str] = None
    is_active: bool = True
    use_count: int = 0
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    store_name: Optional[str] = None


# ── Public intake ─────────────────────────────────────────────────────────────

class TellusIntakeConfig(BaseModel):
    """What the public feedback form needs to render (resolved from token)."""
    brand_name: str
    brand_logo_url: Optional[str] = None
    store_name: Optional[str] = None
    categories: list[str] = Field(default_factory=lambda: list(ReportCategory.__args__))


class TellusFeedbackSubmit(BaseModel):
    category: ReportCategory = "other"
    sentiment: Sentiment = "neutral"
    title: Optional[str] = Field(default=None, max_length=255)
    description: str = Field(min_length=1, max_length=8000)
    occurred_at: Optional[datetime] = None
    reporter_contact: Optional[str] = Field(default=None, max_length=320)
    # Presigned media keys (storage paths returned by /media/presign).
    media_keys: list["TellusSubmittedMedia"] = Field(default_factory=list)
    # Honeypot — bots fill hidden fields; humans leave them empty.
    website: Optional[str] = None


class TellusSubmittedMedia(BaseModel):
    storage_path: str = Field(max_length=1000)
    media_type: MediaType
    mime_type: Optional[str] = Field(default=None, max_length=120)
    file_size: Optional[int] = Field(default=None, ge=0)
    original_filename: Optional[str] = Field(default=None, max_length=400)


class TellusMediaPresignRequest(BaseModel):
    media_type: MediaType
    mime_type: str = Field(max_length=120)
    file_size: int = Field(ge=1)
    original_filename: Optional[str] = Field(default=None, max_length=400)


class TellusMediaPresignResponse(BaseModel):
    upload_url: str
    storage_path: str
    expires_in: int


class TellusFeedbackSubmitResponse(BaseModel):
    report_id: UUID
    report_number: Optional[str] = None
    points_awarded: int = 0
    # True when a logged-in consumer earned points; False for anonymous.
    earned: bool = False


# ── Reports (brand dashboard) ──────────────────────────────────────────────────

class TellusReportMedia(BaseModel):
    id: UUID
    media_type: str
    mime_type: Optional[str] = None
    original_filename: Optional[str] = None
    # Presigned download/playback URL, minted at read time (never stored).
    url: Optional[str] = None


class TellusReport(BaseModel):
    id: UUID
    brand_id: UUID
    store_id: Optional[UUID] = None
    store_name: Optional[str] = None
    report_number: Optional[str] = None
    category: str
    sentiment: str
    title: Optional[str] = None
    description: Optional[str] = None
    occurred_at: Optional[datetime] = None
    reporter_contact: Optional[str] = None
    usefulness_score: int = 0
    status: str
    ai_summary: Optional[str] = None
    ai_category: Optional[str] = None
    ai_sentiment: Optional[str] = None
    moderation_status: str = "visible"
    created_at: datetime
    media: list[TellusReportMedia] = Field(default_factory=list)


class TellusReportStatusUpdate(BaseModel):
    status: ReportStatus


class TellusReportModerate(BaseModel):
    moderation_status: Literal["visible", "flagged", "removed"]


class TellusFeedbackStats(BaseModel):
    total: int = 0
    new: int = 0
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)


# ── Rewards economy ────────────────────────────────────────────────────────────

class TellusPointsBalance(BaseModel):
    account_id: UUID
    points_balance: int = 0
    lifetime_points: int = 0
    level: int = 1
    current_streak: int = 0
    longest_streak: int = 0
    last_activity_date: Optional[Any] = None
    # Derived level progress for the UI.
    points_to_next_level: int = 0
    level_floor: int = 0
    level_ceiling: int = 0


class TellusLedgerEntry(BaseModel):
    id: UUID
    delta: int
    balance_after: int
    reason: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime


class TellusRedeemRequest(BaseModel):
    listing_id: UUID


# ── Marketplace ────────────────────────────────────────────────────────────────

class TellusListingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    image_url: Optional[str] = Field(default=None, max_length=2000)
    points_cost: int = Field(ge=0)
    quantity_total: Optional[int] = Field(default=None, ge=1)
    redemption_type: RedemptionType = "code"
    terms: Optional[str] = Field(default=None, max_length=4000)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    active_from: Optional[datetime] = None
    active_to: Optional[datetime] = None
    is_active: bool = True


class TellusListingUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    image_url: Optional[str] = Field(default=None, max_length=2000)
    points_cost: Optional[int] = Field(default=None, ge=0)
    quantity_total: Optional[int] = Field(default=None, ge=0)
    redemption_type: Optional[RedemptionType] = None
    terms: Optional[str] = Field(default=None, max_length=4000)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    active_from: Optional[datetime] = None
    active_to: Optional[datetime] = None
    is_active: Optional[bool] = None


class TellusListing(BaseModel):
    id: UUID
    brand_id: Optional[UUID] = None
    brand_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    points_cost: int
    quantity_total: Optional[int] = None
    quantity_claimed: int = 0
    quantity_remaining: Optional[int] = None
    redemption_type: str = "code"
    terms: Optional[str] = None
    active_from: Optional[datetime] = None
    active_to: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime


class TellusRedemption(BaseModel):
    id: UUID
    account_id: UUID
    listing_id: UUID
    listing_title: Optional[str] = None
    points_spent: int
    status: str
    code: Optional[str] = None
    issued_at: Optional[datetime] = None
    redeemed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime


class TellusRedemptionStatusUpdate(BaseModel):
    status: Literal["redeemed", "cancelled", "expired"]


# ── Gamification ───────────────────────────────────────────────────────────────

class TellusBadge(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    earned: bool = False
    awarded_at: Optional[datetime] = None


class TellusLeaderboardEntry(BaseModel):
    rank: int
    account_id: UUID
    display_name: str
    lifetime_points: int
    level: int
    is_you: bool = False


# ── Grants ─────────────────────────────────────────────────────────────────────

class TellusGrantRequest(BaseModel):
    """Brand awards bonus points to a consumer for useful feedback."""
    report_id: UUID
    points: int = Field(ge=1, le=5000)
    description: Optional[str] = Field(default=None, max_length=500)


# ── Notifications ──────────────────────────────────────────────────────────────

class TellusNotification(BaseModel):
    id: UUID
    kind: str
    title: str
    body: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    is_read: bool = False
    created_at: datetime


TellusFeedbackSubmit.model_rebuild()
