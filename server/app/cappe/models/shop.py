"""Pydantic shapes — Cappe shop (products/options, orders, checkout, receipt,
inventory, discounts)."""
from datetime import date, datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from ._validators import https_url, ship_country as country_code

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
    # An existing option's id, so an edit UPDATES the row instead of replacing
    # it. Order lines, subscriptions and the stock ledger all point at option
    # ids; a save that minted new ones orphaned every one of them. Omitted →
    # matched by name within its group, else created.
    id: Optional[UUID] = None
    name: str = Field(min_length=1, max_length=120)
    price_delta_cents: int = 0
    sort_order: int = 0
    # Per-variant stock, decremented at checkout. On an EXISTING option this is
    # tri-state: omitted leaves the stock alone, a number sets it, an explicit
    # null stops tracking. A new option with none is untracked.
    inventory: Optional[int] = Field(default=None, ge=0)
    # The stock the editor was showing (see CappeProductUpdate.expected_inventory).
    expected_inventory: Optional[int] = None


class CappeProductOptionGroupInput(BaseModel):
    id: Optional[UUID] = None
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
    subscription_intervals: list[Literal["week", "month"]] = Field(default_factory=list, max_length=2)
    subscription_discount_bps: int = Field(default=0, ge=0, le=5000)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    price_cents: int = Field(default=0, ge=0)
    # Only used if the store row can't be read; the store's currency wins.
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

    @field_validator("subscription_intervals")
    @classmethod
    def unique_subscription_intervals(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Select each subscription interval at most once")
        return value


class CappeProductUpdate(BaseModel):
    subscription_intervals: Optional[list[Literal["week", "month"]]] = Field(default=None, max_length=2)
    subscription_discount_bps: Optional[int] = Field(default=None, ge=0, le=5000)
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    price_cents: Optional[int] = Field(default=None, ge=0)
    # Accepted and ignored: a product is priced in its store's currency.
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
    # The stock the editor was showing when `inventory` was typed. Sent with a
    # stock change so a sale made in between is a 409 instead of being
    # overwritten. Not a column — never written.
    expected_inventory: Optional[int] = None

    @field_validator("subscription_intervals")
    @classmethod
    def unique_subscription_intervals(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Select each subscription interval at most once")
        return value


class CappeProduct(BaseModel):
    subscription_intervals: list[Literal["week", "month"]] = Field(default_factory=list)
    subscription_discount_bps: int = 0
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
    # Public storefront pricing. Owner responses default to the undiscounted
    # shape; public routes populate these from the active promotion calendar.
    discount_percent: int = 0
    discounted_price_cents: Optional[int] = None
    # Approved reviews of this product (public listing only).
    rating_count: int = 0
    rating_avg: Optional[float] = None


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
    restocked_quantity: int = 0
    # This line's share of a promo code's discount.
    promo_discount_cents: int = 0


class CappeOrderRefund(BaseModel):
    """One refund in an order's ledger."""
    id: UUID
    amount_cents: int
    restock: bool = False
    lines: list[dict[str, Any]] = Field(default_factory=list)
    reason: Optional[str] = None
    status: str                      # pending | succeeded | failed
    source: str                      # dashboard | stripe | dispute | manual | legacy
    stripe_refund_id: Optional[str] = None
    failure: Optional[str] = None
    created_at: datetime


class CappeOrder(BaseModel):
    subscription_id: Optional[UUID] = None
    id: UUID
    site_id: UUID
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    status: str
    subtotal_cents: int
    tax_cents: int = 0
    shipping_cents: int = 0
    shipping_address: Optional[dict[str, Any]] = None
    # Where a physical order was priced to ship (two-letter code).
    # The promo code the buyer used and what it took off (subtotal is after it).
    promo_code: Optional[str] = None
    discount_cents: int = 0
    ship_country: Optional[str] = None
    # The refund ledger (detail view and refund responses only).
    refunds: list[CappeOrderRefund] = Field(default_factory=list)
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
    total_cents: Optional[int] = None
    receipt_number: Optional[str] = None
    currency: str
    payment_ref: Optional[str] = None
    note: Optional[str] = None
    requires_approval: bool = False
    approved_at: Optional[datetime] = None
    decline_reason: Optional[str] = None
    # A refund is an event with an amount, not only a status: a PARTIAL refund
    # made in Stripe records its amount here while the status stays paid.
    refunded_at: Optional[datetime] = None
    refunded_cents: int = 0
    # A chargeback opened against the order (Stripe's dispute status), if any.
    dispute_status: Optional[str] = None
    disputed_at: Optional[datetime] = None
    # Approved, waiting for the buyer to pay from the emailed link until then.
    pay_by: Optional[datetime] = None
    shipped_notified_at: Optional[datetime] = None
    platform_fee_cents: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    items: list[CappeOrderItem] = Field(default_factory=list)
    # List view only (the list carries no `items`): enough to tell orders apart.
    item_count: int = 0
    items_summary: Optional[str] = None


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
    """Order PATCH body — status transition and/or tracking edit. All fields
    optional so a tracking-only PATCH never touches status (and so never
    triggers restock); at least one field must be present. Explicit null
    carrier/tracking clears the column (build_patch semantics)."""
    status: Optional[Literal["pending", "paid", "fulfilled", "cancelled", "refunded"]] = None
    carrier: Optional[str] = Field(default=None, max_length=40)
    tracking_number: Optional[str] = Field(default=None, max_length=120)

    @field_validator("carrier", "tracking_number")
    @classmethod
    def _strip_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip() or None

    @model_validator(mode="after")
    def _validate_fields(self):
        # status=None-explicit would SET status = NULL via build_patch → reject.
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        if self.status is None and not ({"carrier", "tracking_number"} & self.model_fields_set):
            raise ValueError("Provide status, carrier, or tracking_number")
        return self


class CappeRefundLine(BaseModel):
    """Units of one order line going back on the shelf with a refund."""
    item_id: UUID
    quantity: int = Field(ge=1, le=100_000)


class CappeRefundRequest(BaseModel):
    """Refund options.

    `amount_cents` omitted → everything still refundable (a full refund).
    `lines` → exactly those units go back to stock (a part refund restocks
    nothing else). `restock` applies to a full refund without `lines`:
    omitted → goods come back to the shelf unless the order was already
    fulfilled (shipped goods are usually not coming back; a lost parcel
    refunded with a restock invents stock)."""
    restock: Optional[bool] = None
    amount_cents: Optional[int] = Field(default=None, ge=1, le=99_999_999)
    lines: list[CappeRefundLine] = Field(default_factory=list, max_length=100)
    reason: Optional[str] = Field(default=None, max_length=500)


class CappeDeliverableUpdate(BaseModel):
    """Owner attaches a delivered result (file URL) to a service/digital line."""
    deliverable_url: str = Field(min_length=1)

    # Released to the buyer on the public receipt page as a link.
    _url_https = field_validator("deliverable_url")(https_url)


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

    @field_validator("selected_option_ids")
    @classmethod
    def unique_options(cls, value):
        if len(value) > 100 or len(value) != len(set(value)):
            raise ValueError("Select each option at most once (maximum 100)")
        return value


class CappeShippingAddressInput(BaseModel):
    """A shipping address typed into the storefront. Collected there only when
    the store takes payment itself; with card payments Stripe asks for it."""
    name: Optional[str] = Field(default=None, max_length=200)
    line1: str = Field(min_length=1, max_length=200)
    line2: Optional[str] = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=120)
    state: Optional[str] = Field(default=None, max_length=120)
    postal_code: Optional[str] = Field(default=None, max_length=32)
    # Omitted = the order's ship-to country (see CappeCheckoutRequest).
    country: Optional[str] = Field(default=None, max_length=2)
    phone: Optional[str] = Field(default=None, max_length=40)
    _country = field_validator("country")(country_code)

    def as_stripe_shape(self, country: Optional[str] = None) -> dict:
        return {
            "name": self.name, "phone": self.phone,
            "address": {
                "line1": self.line1, "line2": self.line2, "city": self.city,
                "state": self.state, "postal_code": self.postal_code,
                "country": self.country or country,
            },
        }


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
    shipping_address: Optional[CappeShippingAddressInput] = None
    # Where the physical lines ship. Priced from the store's zones, stored on
    # the order, and the only country the payment page then accepts. Omitted =
    # the shipping address's country, else the store's home country.
    ship_country: Optional[str] = Field(default=None, max_length=2)
    _ship_country = field_validator("ship_country")(country_code)
    # A promo code (case-blind). Refused with the reason if it can't be used.
    promo_code: Optional[str] = Field(default=None, max_length=40)


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
    # A promo code and what it took off (`subtotal_cents` is after it).
    promo_code: Optional[str] = None
    discount_cents: int = 0
    currency: str
    tax_cents: int = 0
    shipping_cents: int = 0
    total_cents: Optional[int] = None
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
    created_at: datetime
    items: list[CappeReceiptItem] = Field(default_factory=list)
    # Waiting for the store's approval; approved and payable until `pay_by`.
    requires_approval: bool = False
    approved_at: Optional[datetime] = None
    pay_by: Optional[datetime] = None


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


# --- Shipping zones (services/shipping.py) -----------------------------------

class CappeShippingZoneInput(BaseModel):
    """A destination beyond the store's home country, with its own rates."""
    name: str = Field(min_length=1, max_length=80)
    # Two-letter codes. Ignored (stored empty) for the "everywhere else" zone.
    countries: list[str] = Field(default_factory=list, max_length=250)
    rest_of_world: bool = False
    flat_cents: int = Field(default=0, ge=0, le=1_000_000)
    free_threshold_cents: Optional[int] = Field(default=None, ge=0, le=99_999_999)
    # Charge the store's tax rate on goods shipped here (off by default: the
    # rate is the home country's).
    charge_tax: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Give the zone a name")
        return v.strip()

    @field_validator("countries")
    @classmethod
    def _countries(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for code in v:
            code = country_code(code)
            if code not in out:
                out.append(code)
        return out

    @model_validator(mode="after")
    def _rest_has_no_list(self):
        if self.rest_of_world:
            self.countries = []
        return self


class CappeShippingZone(CappeShippingZoneInput):
    id: UUID
    sort_order: int = 0


class CappeShippingZonesReplace(BaseModel):
    zones: list[CappeShippingZoneInput] = Field(default_factory=list, max_length=20)


class CappeShippingZones(BaseModel):
    # Whether the plan includes zones. A downgraded store keeps its zones but
    # ships to its home country only until it upgrades or clears them.
    enabled: bool
    home_country: str
    currency: str
    # Every country a zone can name (Stripe's list), for the picker.
    countries: list[str]
    zones: list[CappeShippingZone] = Field(default_factory=list)


# --- Finances -------------------------------------------------------------------

class CappeFinancialPeriod(BaseModel):
    period: date
    orders: int = 0
    gross_cents: int = 0
    refunds_cents: int = 0


class CappeTopProduct(BaseModel):
    product_id: Optional[UUID] = None
    title: str
    units: int
    revenue_cents: int


class CappeFinancials(BaseModel):
    """Money in, money back and what's left, for one window of days in the
    store's own timezone and currency. Before Stripe's processing fees, which
    Stripe takes on the store's own account and never reports to us."""
    currency: str
    start: date
    end: date
    group: Literal["day", "week", "month"]
    orders: int
    gross_cents: int            # what buyers paid (goods + tax + shipping)
    goods_cents: int
    tax_cents: int
    shipping_cents: int
    platform_fee_cents: int
    refunds_cents: int
    refund_count: int
    net_cents: int              # gross − refunds − platform fees
    average_order_cents: int
    series: list[CappeFinancialPeriod] = Field(default_factory=list)
    top_products: list[CappeTopProduct] = Field(default_factory=list)
    # Orders in the window charged in another currency (before the store's
    # currency changed) — left out of the totals, counted so nothing hides.
    other_currency_orders: int = 0
    export_enabled: bool = False


# --- Promo codes (services/promos.py) ---------------------------------------------

class CappePromoCodeInput(BaseModel):
    """A code buyers type at checkout. Percent (1–90) or a fixed amount off."""
    code: str = Field(min_length=3, max_length=40)
    kind: Literal["percent", "fixed"] = "percent"
    percent_off: Optional[int] = Field(default=None, ge=1, le=90)
    amount_off_cents: Optional[int] = Field(default=None, ge=1, le=99_999_999)
    min_subtotal_cents: Optional[int] = Field(default=None, ge=0, le=99_999_999)
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    max_redemptions: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    once_per_customer: bool = False
    active: bool = True

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        import re
        code = v.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,39}", code):
            raise ValueError("Use 3–40 letters, numbers, dashes or underscores, e.g. SUMMER10")
        return code

    @model_validator(mode="after")
    def _shape(self):
        if self.kind == "percent" and self.percent_off is None:
            raise ValueError("Say how many percent off")
        if self.kind == "fixed" and self.amount_off_cents is None:
            raise ValueError("Say how much off")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("The end date must be on or after the start date")
        if self.kind == "percent":
            self.amount_off_cents = None
        else:
            self.percent_off = None
        return self


class CappePromoCode(CappePromoCodeInput):
    id: UUID
    redemption_count: int = 0
    created_at: datetime


class CappePromoCodes(BaseModel):
    enabled: bool                  # the plan includes promo codes
    currency: str
    codes: list[CappePromoCode] = Field(default_factory=list)


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
    "CappeRefundLine",
    "CappeRefundRequest",
    "CappeOrderRefund",
    "CappeDeliverableUpdate",
    "CappeCartItem",
    "CappeShippingAddressInput",
    "CappeCheckoutRequest",
    "CappeReceiptItem",
    "CappeOrderReceipt",
    "DiscountScope",
    "CappeDiscountInput",
    "CappeDiscountReplace",
    "CappeDiscount",
    "CappeShippingZoneInput",
    "CappeShippingZone",
    "CappeShippingZonesReplace",
    "CappeShippingZones",
    "CappeFinancialPeriod",
    "CappeTopProduct",
    "CappeFinancials",
    "CappePromoCodeInput",
    "CappePromoCode",
    "CappePromoCodes",
]
