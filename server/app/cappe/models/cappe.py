"""Pydantic request/response shapes for Cappe."""
from datetime import datetime, time
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# --- Auth -------------------------------------------------------------------

class CappeSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: Optional[str] = Field(default=None, max_length=255)


class CappeLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class CappeRefreshRequest(BaseModel):
    refresh_token: str


class CappeAccount(BaseModel):
    """The authenticated Cappe identity (returned by require_cappe_account)."""
    id: UUID
    email: str
    name: Optional[str] = None
    plan: str = "free"
    status: str = "active"


class CappeTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    account: CappeAccount


# --- Sites ------------------------------------------------------------------

class CappeSiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: Literal["blank", "byo"] = "blank"
    custom_domain: Optional[str] = Field(default=None, max_length=255)


class CappeSiteFromTemplate(BaseModel):
    template_id: UUID
    name: Optional[str] = Field(default=None, max_length=255)


class CappeSiteUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    custom_domain: Optional[str] = Field(default=None, max_length=255)
    status: Optional[Literal["draft", "published", "archived"]] = None
    theme_config: Optional[dict[str, Any]] = None
    meta_config: Optional[dict[str, Any]] = None
    timezone: Optional[str] = Field(default=None, max_length=64)


class CappeSite(BaseModel):
    id: UUID
    account_id: UUID
    name: str
    slug: str
    subdomain: Optional[str] = None
    custom_domain: Optional[str] = None
    source_type: str
    template_id: Optional[UUID] = None
    status: str
    theme_config: dict[str, Any] = Field(default_factory=dict)
    meta_config: dict[str, Any] = Field(default_factory=dict)
    timezone: str = "UTC"
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    page_count: Optional[int] = None


# --- Pages ------------------------------------------------------------------

class CappePageCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    content: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    status: Literal["draft", "published", "archived"] = "draft"


class CappePageUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    content: Optional[dict[str, Any]] = None
    sort_order: Optional[int] = None
    status: Optional[Literal["draft", "published", "archived"]] = None


class CappePagePreview(BaseModel):
    """Unsaved page content to render for the live editor preview."""
    title: Optional[str] = Field(default=None, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    content: dict[str, Any] = Field(default_factory=dict)


class CappePage(BaseModel):
    id: UUID
    site_id: UUID
    title: str
    slug: str
    content: dict[str, Any] = Field(default_factory=dict)
    sort_order: int
    status: str
    created_at: datetime
    updated_at: datetime


# --- Templates --------------------------------------------------------------

class CappeTemplateSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    category: str
    description: Optional[str] = None
    preview_image_url: Optional[str] = None
    is_premium: bool
    price_cents: int


class CappeTemplateDetail(CappeTemplateSummary):
    structure: dict[str, Any] = Field(default_factory=dict)


# --- Public render ----------------------------------------------------------

class CappePublicSite(BaseModel):
    name: str
    slug: str
    theme_config: dict[str, Any] = Field(default_factory=dict)
    meta_config: dict[str, Any] = Field(default_factory=dict)
    pages: list[CappePage] = Field(default_factory=list)


# ===========================================================================
# Shop
# ===========================================================================

class CappeProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    price_cents: int = Field(default=0, ge=0)
    currency: str = Field(default="USD", max_length=3)
    image_url: Optional[str] = None
    sku: Optional[str] = Field(default=None, max_length=120)
    inventory: Optional[int] = Field(default=None, ge=0)
    status: Literal["active", "draft", "archived"] = "draft"
    sort_order: int = 0


class CappeProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    price_cents: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=3)
    image_url: Optional[str] = None
    sku: Optional[str] = Field(default=None, max_length=120)
    inventory: Optional[int] = Field(default=None, ge=0)
    status: Optional[Literal["active", "draft", "archived"]] = None
    sort_order: Optional[int] = None


class CappeProduct(BaseModel):
    id: UUID
    site_id: UUID
    name: str
    description: Optional[str] = None
    price_cents: int
    currency: str
    image_url: Optional[str] = None
    sku: Optional[str] = None
    inventory: Optional[int] = None
    status: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class CappeOrderItem(BaseModel):
    id: UUID
    product_id: Optional[UUID] = None
    title: str
    unit_price_cents: int
    quantity: int


class CappeOrder(BaseModel):
    id: UUID
    site_id: UUID
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    status: str
    subtotal_cents: int
    currency: str
    payment_ref: Optional[str] = None
    note: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    items: list[CappeOrderItem] = Field(default_factory=list)


class CappeOrderStatusUpdate(BaseModel):
    status: Literal["pending", "paid", "fulfilled", "cancelled", "refunded"]


# Public checkout — client sends product ids + quantities ONLY (price is
# recomputed server-side from the live product rows).
class CappeCartItem(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=10000)


class CappeCheckoutRequest(BaseModel):
    customer_email: EmailStr
    customer_name: Optional[str] = Field(default=None, max_length=255)
    items: list[CappeCartItem] = Field(min_length=1)
    note: Optional[str] = None


# ===========================================================================
# Newsletter
# ===========================================================================

class CappeSubscriberCreate(BaseModel):
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=255)
    source: str = Field(default="manual", max_length=60)


class CappeSubscriber(BaseModel):
    id: UUID
    site_id: UUID
    email: str
    name: Optional[str] = None
    status: str
    source: str
    created_at: datetime
    unsubscribed_at: Optional[datetime] = None


class CappeSubscribeRequest(BaseModel):
    """Public newsletter signup."""
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=255)


class CappeCampaignCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    body_html: Optional[str] = None
    from_name: Optional[str] = Field(default=None, max_length=255)
    scheduled_at: Optional[datetime] = None


class CappeCampaignUpdate(BaseModel):
    subject: Optional[str] = Field(default=None, max_length=500)
    body_html: Optional[str] = None
    from_name: Optional[str] = Field(default=None, max_length=255)
    scheduled_at: Optional[datetime] = None
    status: Optional[Literal["draft", "scheduled", "cancelled"]] = None


class CappeCampaign(BaseModel):
    id: UUID
    site_id: UUID
    subject: str
    body_html: Optional[str] = None
    from_name: Optional[str] = None
    status: str
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    recipient_count: int
    created_at: datetime
    updated_at: datetime


# ===========================================================================
# Forms
# ===========================================================================

class CappeFormField(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(max_length=255)
    type: str = "text"  # text | email | textarea | number | tel | select | checkbox | date
    required: bool = False
    options: Optional[list[str]] = None  # for select


class CappeFormCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    fields: list[CappeFormField] = Field(default_factory=list)
    status: Literal["active", "draft", "archived"] = "active"


class CappeFormUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    fields: Optional[list[CappeFormField]] = None
    status: Optional[Literal["active", "draft", "archived"]] = None


class CappeForm(BaseModel):
    id: UUID
    site_id: UUID
    name: str
    slug: str
    fields: list[dict[str, Any]] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: datetime


class CappeFormSubmission(BaseModel):
    id: UUID
    form_id: UUID
    data: dict[str, Any] = Field(default_factory=dict)
    submitter_email: Optional[str] = None
    is_read: bool
    created_at: datetime


class CappeFormSubmitRequest(BaseModel):
    """Public form submission."""
    data: dict[str, Any] = Field(default_factory=dict)
    submitter_email: Optional[EmailStr] = None


# ===========================================================================
# Bookings
# ===========================================================================

class CappeBookingTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(default=30, gt=0, le=1440)
    price_cents: Optional[int] = Field(default=None, ge=0)
    status: Literal["active", "draft", "archived"] = "active"


class CappeBookingTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, gt=0, le=1440)
    price_cents: Optional[int] = Field(default=None, ge=0)
    status: Optional[Literal["active", "draft", "archived"]] = None


class CappeBookingType(BaseModel):
    id: UUID
    site_id: UUID
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price_cents: Optional[int] = None
    status: str
    created_at: datetime
    updated_at: datetime


class CappeAvailabilitySlot(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    booking_type_id: Optional[UUID] = None


class CappeAvailabilityReplace(BaseModel):
    slots: list[CappeAvailabilitySlot] = Field(default_factory=list)


class CappeAvailability(BaseModel):
    id: UUID
    weekday: int
    start_time: time
    end_time: time
    booking_type_id: Optional[UUID] = None


class CappeBooking(BaseModel):
    id: UUID
    site_id: UUID
    booking_type_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    status: str
    note: Optional[str] = None
    created_at: datetime


class CappeBookingStatusUpdate(BaseModel):
    status: Literal["pending", "confirmed", "cancelled", "completed"]


class CappeBookingRequest(BaseModel):
    """Public booking request — ends_at is computed server-side from the type."""
    booking_type_id: UUID
    starts_at: datetime
    customer_email: EmailStr
    customer_name: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = None


# ===========================================================================
# Blog
# ===========================================================================

class CappePostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    excerpt: Optional[str] = None
    body: Optional[str] = None
    cover_image_url: Optional[str] = None
    status: Literal["draft", "published", "archived"] = "draft"


class CappePostUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    excerpt: Optional[str] = None
    body: Optional[str] = None
    cover_image_url: Optional[str] = None
    status: Optional[Literal["draft", "published", "archived"]] = None


class CappePost(BaseModel):
    id: UUID
    site_id: UUID
    title: str
    slug: str
    excerpt: Optional[str] = None
    body: Optional[str] = None
    cover_image_url: Optional[str] = None
    status: str
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ===========================================================================
# Shared
# ===========================================================================

class CappeUploadResponse(BaseModel):
    url: str
