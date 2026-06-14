"""Pydantic request/response shapes for Cappe."""
import re
from datetime import date, datetime, time
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

# Apex-domain shape (labels 1-63 chars, alnum/hyphen, real-looking TLD).
_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")


def normalize_custom_domain(value: Optional[str]) -> Optional[str]:
    """Normalize an owner-entered custom domain to a bare apex hostname.

    Accepts copy-pasted URLs (scheme/path/port stripped), lowercases, and
    stores the apex (`www.` stripped — the renderer matches both at request
    time). Empty string passes through unchanged: the update route uses
    `'' → NULL` to clear the domain. Rejects domains on our own infrastructure.
    """
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return v
    v = re.sub(r"^https?://", "", v)
    v = v.split("/", 1)[0].split(":", 1)[0].rstrip(".")
    if v.startswith("www."):
        v = v[4:]
    if not _DOMAIN_RE.match(v) or len(v) > 255:
        raise ValueError("Enter a valid domain, like example.com")
    if (
        v == "hey-matcha.com"
        or v.endswith(".hey-matcha.com")
        or v == "localhost"
        or v.endswith(".localhost")
    ):
        raise ValueError("That domain can't be connected")
    return v


# --- Auth -------------------------------------------------------------------

class CappeSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: Optional[str] = Field(default=None, max_length=255)
    # business = an organization's storefront; personal = a solo professional
    # ("business of one") who gets hired/booked. Same engine, different framing.
    account_type: Literal["business", "personal"] = "business"


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
    account_type: str = "business"


class CappeTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    account: CappeAccount


class CappeSignupResponse(BaseModel):
    """Signup result. Real signups must confirm their email first
    (`verification_required=True`, no tokens). Reserved test-domain signups
    (which the email guard won't deliver to) auto-verify and get tokens inline
    so dev/seed flows still work."""
    verification_required: bool
    email: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    account: Optional[CappeAccount] = None


class CappeVerifyRequest(BaseModel):
    token: str


class CappeResendRequest(BaseModel):
    email: EmailStr


# --- Sites ------------------------------------------------------------------

class CappeSiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: Literal["blank", "byo"] = "blank"
    custom_domain: Optional[str] = Field(default=None, max_length=255)

    _norm_domain = field_validator("custom_domain")(normalize_custom_domain)


class CappeSiteFromTemplate(BaseModel):
    template_id: UUID
    name: Optional[str] = Field(default=None, max_length=255)


class CappeSiteUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    # The tenant subdomain (<sub>.gummfit.com). Editable after creation; the
    # route slugifies + checks reserved/uniqueness before applying.
    subdomain: Optional[str] = Field(default=None, max_length=140)
    custom_domain: Optional[str] = Field(default=None, max_length=255)

    _norm_domain = field_validator("custom_domain")(normalize_custom_domain)
    status: Optional[Literal["draft", "published", "archived"]] = None
    theme_config: Optional[dict[str, Any]] = None
    meta_config: Optional[dict[str, Any]] = None
    timezone: Optional[str] = Field(default=None, max_length=64)


class CappeReadinessItem(BaseModel):
    """One launch-checklist row. `action` is a relative hint the UI turns into
    a deep link (e.g. 'shop', 'pages', 'settings')."""
    key: str
    label: str
    hint: str
    done: bool
    required: bool
    action: Optional[str] = None


class CappeReadiness(BaseModel):
    ready: bool                       # all REQUIRED items done → publishable
    items: list[CappeReadinessItem] = Field(default_factory=list)


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
    """Unsaved page content to render for the live editor preview.

    `theme_config` lets the editor preview an unsaved theme (live theme
    switching) — when omitted, the site's saved theme is used."""
    title: Optional[str] = Field(default=None, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    content: dict[str, Any] = Field(default_factory=dict)
    theme_config: Optional[dict[str, Any]] = None


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

# A product is a general "offering"; `fulfillment` decides how it's delivered.
#   physical - shipped good (uses inventory)
#   digital  - buyer downloads `digital_file_url`
#   service  - seller delivers a result; buyer answers `intake_fields`
#   booking  - buying schedules a session against `booking_type_id`
Fulfillment = Literal["physical", "digital", "service", "booking"]


# Option groups (Size, Milk, Add-ons). `single` = pick ≤1 (a radio); `multi` =
# pick any (checkboxes). Each option carries a SIGNED price delta. The whole set
# is replaced on product create/update (mirrors availability/rate-rule replace).
class CappeProductOptionInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price_delta_cents: int = 0
    sort_order: int = 0


class CappeProductOptionGroupInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    select_type: Literal["single", "multi"] = "single"
    required: bool = False
    sort_order: int = 0
    options: list[CappeProductOptionInput] = Field(default_factory=list)


class CappeProductOption(BaseModel):
    id: UUID
    name: str
    price_delta_cents: int = 0
    sort_order: int = 0


class CappeProductOptionGroup(BaseModel):
    id: UUID
    name: str
    select_type: str = "single"
    required: bool = False
    sort_order: int = 0
    options: list[CappeProductOption] = Field(default_factory=list)


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
    fulfillment: Fulfillment = "physical"
    digital_file_url: Optional[str] = None
    booking_type_id: Optional[UUID] = None
    requires_approval: bool = False
    # Intake questions for service/booking offerings; same shape as form fields:
    # [{key,label,type,required,options?}].
    intake_fields: list[dict[str, Any]] = Field(default_factory=list)
    category: Optional[str] = Field(default=None, max_length=120)
    # None = leave option groups untouched; [] = clear them.
    option_groups: Optional[list[CappeProductOptionGroupInput]] = None


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
    fulfillment: Optional[Fulfillment] = None
    digital_file_url: Optional[str] = None
    booking_type_id: Optional[UUID] = None
    requires_approval: Optional[bool] = None
    intake_fields: Optional[list[dict[str, Any]]] = None
    category: Optional[str] = Field(default=None, max_length=120)
    option_groups: Optional[list[CappeProductOptionGroupInput]] = None


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
    fulfillment: str = "physical"
    digital_file_url: Optional[str] = None
    booking_type_id: Optional[UUID] = None
    requires_approval: bool = False
    intake_fields: list[dict[str, Any]] = Field(default_factory=list)
    category: Optional[str] = None
    option_groups: list[CappeProductOptionGroup] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    # Storefront display only — best active discount for this product (0 if none).
    # Order pricing is still recomputed server-side at checkout.
    discount_percent: int = 0
    discounted_price_cents: Optional[int] = None


class CappeOrderItem(BaseModel):
    id: UUID
    product_id: Optional[UUID] = None
    title: str
    unit_price_cents: int
    quantity: int
    fulfillment: str = "physical"
    intake_answers: dict[str, Any] = Field(default_factory=dict)
    # Snapshot of chosen options at purchase: [{group, name, price_delta_cents}].
    selected_options: list[dict[str, Any]] = Field(default_factory=list)
    deliverable_url: Optional[str] = None
    booking_id: Optional[UUID] = None


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
    requires_approval: bool = False
    approved_at: Optional[datetime] = None
    decline_reason: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    items: list[CappeOrderItem] = Field(default_factory=list)


# --- Approval queue (unified bookings + orders awaiting the creator) ---------

class CappeRequestSummary(BaseModel):
    """One row in the creator's accept/decline queue."""
    kind: Literal["booking", "order"]
    id: UUID
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    title: str                         # booking type name / order summary
    amount_cents: Optional[int] = None
    currency: str = "USD"
    starts_at: Optional[datetime] = None
    note: Optional[str] = None
    rider_acknowledged: Optional[bool] = None
    created_at: datetime


class CappeOrderStatusUpdate(BaseModel):
    status: Literal["pending", "paid", "fulfilled", "cancelled", "refunded"]


class CappeDeliverableUpdate(BaseModel):
    """Owner attaches a delivered result (file URL) to a service/digital line."""
    deliverable_url: str = Field(min_length=1)


# Public checkout — client sends product ids + quantities ONLY (price is
# recomputed server-side from the live product rows). Service/booking lines may
# carry per-line intake answers; booking lines carry the chosen start time.
class CappeCartItem(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=10000)
    intake_answers: dict[str, Any] = Field(default_factory=dict)
    starts_at: Optional[datetime] = None  # required for booking-fulfillment items
    # Chosen option ids; the server validates + prices them (never trusts deltas).
    selected_option_ids: list[UUID] = Field(default_factory=list)


class CappeCheckoutRequest(BaseModel):
    customer_email: EmailStr
    customer_name: Optional[str] = Field(default=None, max_length=255)
    items: list[CappeCartItem] = Field(min_length=1)
    note: Optional[str] = None


# Buyer-facing receipt (resolved by the order's unguessable access_token).
class CappeReceiptItem(BaseModel):
    title: str
    quantity: int
    fulfillment: str
    unit_price_cents: int
    selected_options: list[dict[str, Any]] = Field(default_factory=list)
    download_url: Optional[str] = None       # digital — only when paid/fulfilled
    deliverable_url: Optional[str] = None    # service — only when paid/fulfilled
    booking_starts_at: Optional[datetime] = None
    booking_ends_at: Optional[datetime] = None
    booking_status: Optional[str] = None


class CappeOrderReceipt(BaseModel):
    order_id: UUID
    status: str
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    subtotal_cents: int
    currency: str
    created_at: datetime
    items: list[CappeReceiptItem] = Field(default_factory=list)


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

# pricing_mode: flat = price_cents is the whole-booking price; hourly =
# price_cents is the base rate per hour, scaled by matching rate rules.
BookingPricingMode = Literal["flat", "hourly"]


class CappeBookingTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(default=30, gt=0, le=1440)
    price_cents: Optional[int] = Field(default=None, ge=0)
    status: Literal["active", "draft", "archived"] = "active"
    requires_approval: bool = False
    pricing_mode: BookingPricingMode = "flat"


class CappeBookingTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, gt=0, le=1440)
    price_cents: Optional[int] = Field(default=None, ge=0)
    status: Optional[Literal["active", "draft", "archived"]] = None
    requires_approval: Optional[bool] = None
    pricing_mode: Optional[BookingPricingMode] = None


class CappeBookingType(BaseModel):
    id: UUID
    site_id: UUID
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price_cents: Optional[int] = None
    status: str
    requires_approval: bool = False
    pricing_mode: str = "flat"
    created_at: datetime
    updated_at: datetime


# --- Rate rules (dynamic time-of-day pricing) -------------------------------

class CappeRateRuleInput(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    booking_type_id: Optional[UUID] = None  # None = applies to every booking type
    weekday: Optional[int] = Field(default=None, ge=0, le=6)  # None = every day (Mon=0..Sun=6)
    start_time: time
    end_time: time
    multiplier: float = Field(default=1.0, ge=0, le=100)


class CappeRateRulesReplace(BaseModel):
    rules: list[CappeRateRuleInput] = Field(default_factory=list)


class CappeRateRule(BaseModel):
    id: UUID
    site_id: UUID
    booking_type_id: Optional[UUID] = None
    label: str
    weekday: Optional[int] = None
    start_time: time
    end_time: time
    multiplier: float
    created_at: datetime


# --- Rider (Pro, personal creators) -----------------------------------------

class CappeRiderItemInput(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    detail: Optional[str] = None
    is_required: bool = True
    sort_order: int = 0


class CappeRiderReplace(BaseModel):
    items: list[CappeRiderItemInput] = Field(default_factory=list)


class CappeRiderItem(BaseModel):
    id: UUID
    site_id: UUID
    label: str
    detail: Optional[str] = None
    is_required: bool
    sort_order: int
    created_at: datetime


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
    requires_approval: bool = False
    quoted_price_cents: Optional[int] = None
    approved_at: Optional[datetime] = None
    decline_reason: Optional[str] = None
    rider_acknowledged: bool = False
    rider_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class CappeBookingStatusUpdate(BaseModel):
    status: Literal["pending", "confirmed", "cancelled", "completed"]


class CappeApprovalDecline(BaseModel):
    """Creator declines a pending booking/order, with an optional reason that's
    surfaced on the buyer's receipt."""
    reason: Optional[str] = Field(default=None, max_length=1000)


class CappeBookingRequest(BaseModel):
    """Public booking request. For hourly-priced types the buyer may pick an
    `ends_at` (variable length); otherwise the type's duration is used.
    `rider_acknowledged` must be true when the site has required rider items."""
    booking_type_id: UUID
    starts_at: datetime
    ends_at: Optional[datetime] = None
    customer_email: EmailStr
    customer_name: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = None
    rider_acknowledged: bool = False


class CappeBookingQuoteRequest(BaseModel):
    """Public price quote for a prospective booking (no write)."""
    booking_type_id: UUID
    starts_at: datetime
    ends_at: Optional[datetime] = None


class CappeBookingReschedule(BaseModel):
    """Customer self-serve reschedule — a new start (and end for hourly types)."""
    starts_at: datetime
    ends_at: Optional[datetime] = None


class CappePublicBooking(BaseModel):
    """Customer-facing booking view, resolved by the unguessable access token."""
    status: str
    type_name: str
    site_name: str
    slug: str                              # for fetching reschedule slots
    booking_type_id: Optional[UUID] = None
    starts_at: datetime
    ends_at: datetime
    quoted_price_cents: Optional[int] = None
    timezone: str
    can_modify: bool      # cancel/reschedule allowed (future + pending/confirmed)


class CappeBookingQuote(BaseModel):
    price_cents: int                                  # final, after any discount
    currency: str = "USD"
    pricing_mode: str
    requires_approval: bool
    duration_minutes: int
    original_price_cents: Optional[int] = None        # pre-discount (None if no discount)
    discount_percent: int = 0


# --- Discounts (creator-set promotions) -------------------------------------

DiscountScope = Literal["all", "booking_type", "product"]


class CappeDiscountInput(BaseModel):
    label: str = Field(default="Discount", min_length=1, max_length=120)
    percent_off: int = Field(ge=1, le=90)
    scope: DiscountScope = "all"
    target_id: Optional[UUID] = None          # required when scope != 'all'
    active: bool = True
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None


class CappeDiscountReplace(BaseModel):
    discounts: list[CappeDiscountInput] = Field(default_factory=list)


class CappeDiscount(BaseModel):
    id: UUID
    site_id: UUID
    label: str
    percent_off: int
    scope: str
    target_id: Optional[UUID] = None
    active: bool
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    created_at: datetime


# ===========================================================================
# Messages (creator ↔ client inbox)
# ===========================================================================

class CappeMessage(BaseModel):
    id: UUID
    thread_id: UUID
    sender: Literal["owner", "client"]
    body: str
    created_at: datetime


class CappeThread(BaseModel):
    id: UUID
    site_id: UUID
    client_email: str
    client_name: Optional[str] = None
    subject: Optional[str] = None
    status: str
    booking_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    owner_unread: int = 0
    last_message_at: datetime
    created_at: datetime
    last_snippet: Optional[str] = None  # populated in list view


class CappeThreadDetail(CappeThread):
    access_token: UUID
    messages: list[CappeMessage] = Field(default_factory=list)


class CappeThreadCreate(BaseModel):
    """Owner starts a conversation with a client."""
    client_email: EmailStr
    client_name: Optional[str] = Field(default=None, max_length=255)
    subject: Optional[str] = Field(default=None, max_length=300)
    body: str = Field(min_length=1, max_length=10000)
    booking_id: Optional[UUID] = None
    order_id: Optional[UUID] = None


class CappeMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


# Public (token-resolved) thread view for the client.
class CappePublicThread(BaseModel):
    site_name: str
    subject: Optional[str] = None
    messages: list[CappeMessage] = Field(default_factory=list)


# ===========================================================================
# Clients (derived directory of people who've interacted with a site)
# ===========================================================================

class CappeClient(BaseModel):
    email: str
    name: Optional[str] = None
    orders_count: int = 0
    bookings_count: int = 0
    is_subscriber: bool = False
    has_thread: bool = False
    total_spent_cents: int = 0
    last_activity: Optional[datetime] = None


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
# Reviews
# ===========================================================================

class CappeReviewCreate(BaseModel):
    """Public review submission from a published site."""
    author_name: str = Field(min_length=1, max_length=120)
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=1, max_length=2000)


class CappeReviewModerate(BaseModel):
    """Creator moderation action."""
    status: Literal["approved", "hidden", "pending"]


class CappeReview(BaseModel):
    id: UUID
    site_id: UUID
    author_name: str
    rating: Optional[int] = None
    body: str
    status: str
    created_at: datetime


class CappePublicReview(BaseModel):
    """Approved review as shown on the public site."""
    author_name: str
    rating: Optional[int] = None
    body: str
    created_at: datetime


# ===========================================================================
# Shared
# ===========================================================================

class CappeUploadResponse(BaseModel):
    url: str
