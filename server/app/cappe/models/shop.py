"""Pydantic shapes — Cappe shop (products/options, orders, checkout, receipt,
inventory, discounts)."""
from datetime import date, datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

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
    # Per-variant stock (NULL = untracked/unlimited). Decremented at checkout.
    inventory: Optional[int] = Field(default=None, ge=0)


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
    inventory: Optional[int] = None


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
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)
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
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)
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
    low_stock_threshold: Optional[int] = None
    status: str
    sort_order: int
    fulfillment: str = "physical"
    digital_file_url: Optional[str] = None
    booking_type_id: Optional[UUID] = None
    requires_approval: bool = False
    intake_fields: list[dict[str, Any]] = Field(default_factory=list)
    category: Optional[str] = None
    option_groups: list[CappeProductOptionGroup] = Field(default_factory=list)


class CappeStockAdjust(BaseModel):
    """Manual stock change from the owner (restock, damage, correction, …)."""
    delta: int                                   # signed; new balance clamped at 0
    option_id: Optional[UUID] = None             # adjust a variant instead of the product
    reason: Literal["manual", "restock", "damage", "return", "adjustment"] = "manual"
    note: Optional[str] = Field(default=None, max_length=1000)


class CappeInventoryAdjustment(BaseModel):
    id: UUID
    product_id: UUID
    option_id: Optional[UUID] = None
    delta: int
    balance_after: Optional[int] = None
    reason: str
    note: Optional[str] = None
    created_at: datetime
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
    tax_cents: int = 0
    total_cents: Optional[int] = None
    receipt_number: Optional[str] = None
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
    items: list[CappeCartItem] = Field(min_length=1, max_length=100)
    note: Optional[str] = None
    # Where Stripe Checkout returns the buyer (passed by the storefront widget,
    # which knows its own published URL). Optional — absent → no card payment,
    # order stays pending for manual handling.
    success_url: Optional[str] = Field(default=None, max_length=2000)
    cancel_url: Optional[str] = Field(default=None, max_length=2000)


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
    location_id: Optional[UUID] = None         # NULL = applies at all locations


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
    location_id: Optional[UUID] = None
    created_at: datetime


__all__ = [
    "Fulfillment",
    "CappeProductOptionInput",
    "CappeProductOptionGroupInput",
    "CappeProductOption",
    "CappeProductOptionGroup",
    "CappeProductCreate",
    "CappeProductUpdate",
    "CappeProduct",
    "CappeStockAdjust",
    "CappeInventoryAdjustment",
    "CappeOrderItem",
    "CappeOrder",
    "CappeRequestSummary",
    "CappeOrderStatusUpdate",
    "CappeDeliverableUpdate",
    "CappeCartItem",
    "CappeCheckoutRequest",
    "CappeReceiptItem",
    "CappeOrderReceipt",
    "DiscountScope",
    "CappeDiscountInput",
    "CappeDiscountReplace",
    "CappeDiscount",
]
