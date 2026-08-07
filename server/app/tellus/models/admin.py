"""Pydantic request/response shapes for the Tell-Us internal admin management
system (require_tellus_admin surfaces only — accounts, brands, moderation,
economy config, audit trail).
"""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# Must match ck_tellus_accounts_status (tellus_app_08).
ACCOUNT_STATUSES = ("active", "suspended")


class TellusAdminAccountSummary(BaseModel):
    id: UUID
    email: str
    display_name: Optional[str] = None
    account_type: Literal["consumer", "brand"]
    status: str
    email_verified: bool
    city: Optional[str] = None
    state: Optional[str] = None
    created_at: datetime
    points_balance: int = 0
    report_count: int = 0
    brand_id: Optional[UUID] = None
    brand_name: Optional[str] = None


class TellusAdminAccountList(BaseModel):
    items: list[TellusAdminAccountSummary]
    total: int
    limit: int
    offset: int


class TellusAdminLedgerEntry(BaseModel):
    id: UUID
    delta: int
    balance_after: int
    reason: str
    event_key: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime


class TellusAdminAuditEntry(BaseModel):
    id: UUID
    actor_email: str
    action: str
    target_type: str
    target_id: Optional[str] = None
    detail: Optional[dict] = None
    created_at: datetime


class TellusAdminAccountDetail(BaseModel):
    account: TellusAdminAccountSummary
    lifetime_points: int = 0
    level: int = 1
    current_streak: int = 0
    ledger: list[TellusAdminLedgerEntry] = []
    recent_reports: list[dict] = []
    redemptions: list[dict] = []
    dm_threads: list[dict] = []
    audit: list[TellusAdminAuditEntry] = []


class TellusAdminSuspendRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


class TellusAdminPasswordResetResponse(BaseModel):
    reset_url: str
    expires_in_minutes: int = 60


class TellusAdminPointsAdjust(BaseModel):
    delta: int
    description: str = Field(..., min_length=3, max_length=300)
    idempotency_key: Optional[str] = Field(None, max_length=80)
    clamp: bool = False

    @field_validator("delta")
    @classmethod
    def _nonzero_bounded(cls, v: int) -> int:
        if v == 0:
            raise ValueError("delta must be non-zero")
        if abs(v) > 100_000:
            raise ValueError("delta out of range (±100,000)")
        return v


class TellusAdminBrandSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    plan_status: Literal["pending", "active", "past_due", "canceled"]
    source: Literal["signup", "consumer_added"]
    owner_account_id: Optional[UUID] = None
    owner_email: Optional[str] = None
    location_count: int
    store_count: int
    has_stripe_subscription: bool = False
    created_at: datetime


class TellusAdminBrandList(BaseModel):
    items: list[TellusAdminBrandSummary]
    total: int
    limit: int
    offset: int


class TellusAdminBrandDetail(BaseModel):
    brand: TellusAdminBrandSummary
    activated_at: Optional[datetime] = None
    claimed_at: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stores: list[dict] = []
    links: list[dict] = []
    prompts: list[dict] = []
    report_stats: dict = {}
    audit: list[TellusAdminAuditEntry] = []


class TellusAdminPlanAction(BaseModel):
    action: Literal["comp", "cancel"]
    note: Optional[str] = Field(None, max_length=500)


class TellusAdminAssignOwner(BaseModel):
    account_id: UUID


class TellusAdminModerationUpdate(BaseModel):
    moderation_status: Literal["visible", "flagged", "removed"]
    note: Optional[str] = Field(None, max_length=500)


class TellusAdminDmThreadSummary(BaseModel):
    id: UUID
    report_id: UUID
    brand_name: str
    consumer_email: str
    blocked: bool
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime


class TellusAdminEarningRule(BaseModel):
    # NOTE: tellus_earning_rules has NO updated_at column — don't add one here.
    event_key: str
    points: int
    daily_cap: Optional[int] = None
    cooldown_seconds: Optional[int] = None
    is_active: bool


class TellusAdminEarningRuleUpdate(BaseModel):
    # PATCH semantics via model_dump(exclude_unset=True): explicit null CLEARS
    # daily_cap/cooldown_seconds, absent leaves the column alone.
    points: Optional[int] = Field(None, ge=0, le=10_000)
    daily_cap: Optional[int] = Field(None, ge=0, le=100_000)
    cooldown_seconds: Optional[int] = Field(None, ge=0, le=604_800)
    is_active: Optional[bool] = None


class TellusAdminBadge(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    criteria: dict = {}
    sort_order: int = 0
    award_count: int = 0


class TellusAdminBadgeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=300)
    threshold: Optional[int] = Field(None, ge=1, le=100_000)


class TellusAdminListingUpdate(BaseModel):
    is_active: bool


class TellusAdminBoardPostRow(BaseModel):
    id: UUID
    board_id: UUID
    brand_id: UUID
    brand_name: str
    kind: str
    title: str
    moderation_status: str
    author_display_name: Optional[str] = None
    created_at: datetime


class TellusAdminBoardReplyRow(BaseModel):
    id: UUID
    post_id: UUID
    post_title: str
    brand_id: UUID
    brand_name: str
    author_display_name: str
    body: str
    status: str
    created_at: datetime


class TellusAdminBoardReplyStatusUpdate(BaseModel):
    # Force ANY transition — bypasses board_service.can_reply_transition by
    # design (that's the point of an admin override).
    status: Literal["held", "approved", "rejected", "removed"]


class TellusPasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=16)
    new_password: str = Field(..., min_length=8, max_length=128)
