"""Pydantic shapes — Cappe billing (plans, subscriptions, add-ons, admin)."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

BillingInterval = Literal["month", "year"]


# --- Public catalog ---------------------------------------------------------

class CappePlanPrice(BaseModel):
    interval: str
    unit_amount_cents: int
    currency: str = "USD"
    # False when the Stripe Price has not been minted yet — the seed script
    # hasn't run for this environment, so the plan cannot be purchased.
    purchasable: bool = True


class CappePlan(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    status: str = "active"
    sort_order: int = 0
    can_sell: bool = False
    platform_fee_bps: int = 0
    allowed_fulfillment: list[str] = Field(default_factory=list)
    site_limit: Optional[int] = None
    mailbox_quota_included: int = 0
    premium_design: bool = False
    features: dict[str, Any] = Field(default_factory=dict)
    prices: list[CappePlanPrice] = Field(default_factory=list)
    intro_price_cents: Optional[int] = None
    intro_days: Optional[int] = None


class CappeAddon(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    unit_label: str = "unit"
    max_quantity: int = 100
    prices: list[CappePlanPrice] = Field(default_factory=list)


class CappeCatalog(BaseModel):
    plans: list[CappePlan] = Field(default_factory=list)
    addons: list[CappeAddon] = Field(default_factory=list)
    # Whether THIS account may still claim the $1 intro.
    intro_available: bool = False


# --- Tenant subscription ----------------------------------------------------

class CappeSubscriptionAddon(BaseModel):
    code: str
    name: str
    unit_label: str
    quantity: int


class CappeSubscription(BaseModel):
    plan_code: str
    plan_name: Optional[str] = None
    interval: str = "month"
    status: str
    source: str = "stripe"
    current_period_end: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    comped_until: Optional[datetime] = None
    addons: list[CappeSubscriptionAddon] = Field(default_factory=list)


class CappeCheckoutRequest(BaseModel):
    plan_code: str = Field(max_length=40)
    interval: BillingInterval = "month"
    success_url: str = Field(max_length=2000)
    cancel_url: str = Field(max_length=2000)
    # NOTE: there is deliberately no `intro` field. Whether the $1 offer applies
    # is decided server-side from the account's own history — a client-supplied
    # flag would be a free-money endpoint.


class CappeCheckoutResponse(BaseModel):
    checkout_url: str
    intro_applied: bool = False


class CappePortalRequest(BaseModel):
    return_url: str = Field(max_length=2000)


class CappePortalResponse(BaseModel):
    portal_url: str


class CappeAddonQuantityRequest(BaseModel):
    addon_code: str = Field(max_length=40)
    quantity: int = Field(ge=0, le=1000)


class CappeCancelRequest(BaseModel):
    at_period_end: bool = True


# --- Admin ------------------------------------------------------------------

class CappePlanUpsert(BaseModel):
    """Create/update a catalog row. Every field optional on PATCH — only what
    the caller sends is written."""
    name: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = None
    status: Optional[Literal["active", "legacy", "archived"]] = None
    sort_order: Optional[int] = None
    can_sell: Optional[bool] = None
    platform_fee_bps: Optional[int] = Field(default=None, ge=0, le=5000)
    allowed_fulfillment: Optional[list[Literal["physical", "digital", "service", "booking"]]] = None
    site_limit: Optional[int] = Field(default=None, ge=0)
    mailbox_quota_included: Optional[int] = Field(default=None, ge=0)
    premium_design: Optional[bool] = None
    features: Optional[dict[str, Any]] = None
    unit_label: Optional[str] = Field(default=None, max_length=50)
    max_quantity: Optional[int] = Field(default=None, ge=1)


class CappePlanCreate(CappePlanUpsert):
    code: str = Field(max_length=40, pattern=r"^[a-z0-9_]+$")
    kind: Literal["plan", "addon"] = "plan"
    name: str = Field(max_length=120)


class CappePriceCreate(BaseModel):
    """A price change MINTS A NEW Stripe Price — they are immutable — and
    supersedes the current row. Existing subscribers are grandfathered."""
    interval: Literal["month", "year", "once"]
    unit_amount_cents: int = Field(ge=0)
    currency: str = Field(default="USD", max_length=3)
    role: Literal["standard", "intro"] = "standard"
    intro_days: Optional[int] = Field(default=None, ge=1, le=365)


class CappePriceOut(BaseModel):
    id: UUID
    product_code: str
    role: str
    interval: str
    unit_amount_cents: int
    currency: str
    intro_days: Optional[int] = None
    stripe_price_id: Optional[str] = None
    lookup_key: Optional[str] = None
    is_current: bool
    active: bool
    created_at: datetime
    archived_at: Optional[datetime] = None


class CappeAdminAccount(BaseModel):
    id: UUID
    email: str
    name: Optional[str] = None
    plan: str
    account_type: str
    status: str
    is_platform_admin: bool = False
    subscription_status: Optional[str] = None
    subscription_source: Optional[str] = None
    comped_until: Optional[datetime] = None
    created_at: Optional[datetime] = None


class CappeCompRequest(BaseModel):
    plan_code: str = Field(max_length=40)
    until: Optional[datetime] = None
    reason: str = Field(min_length=3, max_length=500)


class CappePlatformAdminRequest(BaseModel):
    is_platform_admin: bool


__all__ = [
    "BillingInterval",
    "CappePlanPrice",
    "CappePlan",
    "CappeAddon",
    "CappeCatalog",
    "CappeSubscriptionAddon",
    "CappeSubscription",
    "CappeCheckoutRequest",
    "CappeCheckoutResponse",
    "CappePortalRequest",
    "CappePortalResponse",
    "CappeAddonQuantityRequest",
    "CappeCancelRequest",
    "CappePlanUpsert",
    "CappePlanCreate",
    "CappePriceCreate",
    "CappePriceOut",
    "CappeAdminAccount",
    "CappeCompRequest",
    "CappePlatformAdminRequest",
]
