"""Pydantic shapes — Cappe bookings (booking types, availability, rate rules,
rider, locations, staff, bookings/quotes)."""
from datetime import datetime, time
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# pricing_mode: flat = price_cents is the whole-booking price; hourly =
# price_cents is the base rate per hour, scaled by matching rate rules.
BookingPricingMode = Literal["flat", "hourly"]


# --- Locations (multi-location: LA, San Diego, …) ---------------------------
# Booking config rows carry a NULLABLE location_id (NULL = "all locations /
# main"), so a single-location site is unchanged.

class CappeLocationHours(BaseModel):
    day: int = Field(ge=0, le=6)          # Mon=0..Sun=6
    open: Optional[str] = Field(default=None, max_length=5)   # "HH:MM"
    close: Optional[str] = Field(default=None, max_length=5)
    closed: bool = False


class CappeLocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    timezone: Optional[str] = Field(default=None, max_length=64)
    hours: list[CappeLocationHours] = Field(default_factory=list)
    contact_phone: Optional[str] = Field(default=None, max_length=64)
    contact_email: Optional[EmailStr] = None
    is_default: bool = False
    active: bool = True
    sort_order: int = 0


class CappeLocationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    timezone: Optional[str] = Field(default=None, max_length=64)
    hours: Optional[list[CappeLocationHours]] = None
    contact_phone: Optional[str] = Field(default=None, max_length=64)
    contact_email: Optional[EmailStr] = None
    is_default: Optional[bool] = None
    active: Optional[bool] = None
    sort_order: Optional[int] = None


class CappeLocation(BaseModel):
    id: UUID
    site_id: UUID
    name: str
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    timezone: Optional[str] = None
    hours: list[dict[str, Any]] = Field(default_factory=list)
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    is_default: bool = False
    active: bool = True
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


# --- Staff / stylists -------------------------------------------------------

class CappeStaffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    bio: Optional[str] = None
    image_url: Optional[str] = None
    active: bool = True
    sort_order: int = 0
    location_id: Optional[UUID] = None  # NULL = works at all locations


class CappeStaffUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    bio: Optional[str] = None
    image_url: Optional[str] = None
    active: Optional[bool] = None
    sort_order: Optional[int] = None
    location_id: Optional[UUID] = None


class CappeStaff(BaseModel):
    id: UUID
    site_id: UUID
    name: str
    bio: Optional[str] = None
    image_url: Optional[str] = None
    active: bool = True
    sort_order: int = 0
    location_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class CappeStaffImportError(BaseModel):
    row: int                            # 1-based data row (header excluded)
    name: Optional[str] = None
    reason: str


class CappeStaffImportResult(BaseModel):
    total: int = 0                      # data rows seen
    created: int = 0
    updated: int = 0                    # matched an existing staff name (location/bio updated)
    skipped: int = 0
    branches_matched: int = 0           # rows that resolved a branch by name
    errors: list[CappeStaffImportError] = Field(default_factory=list)


class CappeBookingTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(default=30, gt=0, le=1440)
    price_cents: Optional[int] = Field(default=None, ge=0)
    status: Literal["active", "draft", "archived"] = "active"
    requires_approval: bool = False
    pricing_mode: BookingPricingMode = "flat"
    category: Optional[str] = Field(default=None, max_length=120)
    buffer_minutes: int = Field(default=0, ge=0, le=240)
    # Staff who perform this service; None = leave as-is, [] = unstaffed (shared
    # calendar). A staffed service is only bookable with one of these staff.
    staff_ids: Optional[list[UUID]] = None
    location_id: Optional[UUID] = None  # NULL = offered at all locations


class CappeBookingTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, gt=0, le=1440)
    price_cents: Optional[int] = Field(default=None, ge=0)
    status: Optional[Literal["active", "draft", "archived"]] = None
    requires_approval: Optional[bool] = None
    pricing_mode: Optional[BookingPricingMode] = None
    category: Optional[str] = Field(default=None, max_length=120)
    buffer_minutes: Optional[int] = Field(default=None, ge=0, le=240)
    staff_ids: Optional[list[UUID]] = None
    location_id: Optional[UUID] = None


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
    category: Optional[str] = None
    buffer_minutes: int = 0
    staff_ids: list[UUID] = Field(default_factory=list)
    location_id: Optional[UUID] = None
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
    location_id: Optional[UUID] = None  # NULL = applies at all locations


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
    location_id: Optional[UUID] = None
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
    staff_id: Optional[UUID] = None  # None = a site-wide window any staff can use
    location_id: Optional[UUID] = None  # None = applies at all locations


class CappeAvailabilityReplace(BaseModel):
    slots: list[CappeAvailabilitySlot] = Field(default_factory=list)


class CappeAvailability(BaseModel):
    id: UUID
    weekday: int
    start_time: time
    end_time: time
    booking_type_id: Optional[UUID] = None
    staff_id: Optional[UUID] = None
    location_id: Optional[UUID] = None


class CappeBooking(BaseModel):
    id: UUID
    site_id: UUID
    booking_type_id: Optional[UUID] = None
    staff_id: Optional[UUID] = None
    staff_name: Optional[str] = None
    location_id: Optional[UUID] = None
    location_name: Optional[str] = None
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
    staff_id: Optional[UUID] = None  # None = "any available" (auto-assigned)
    location_id: Optional[UUID] = None  # None = single/main location


class CappeBookingQuoteRequest(BaseModel):
    """Public price quote for a prospective booking (no write)."""
    booking_type_id: UUID
    starts_at: datetime
    ends_at: Optional[datetime] = None
    location_id: Optional[UUID] = None


class CappeBookingReschedule(BaseModel):
    """Customer self-serve reschedule — a new start (and end for hourly types)."""
    starts_at: datetime
    ends_at: Optional[datetime] = None


class CappeBookingQuote(BaseModel):
    price_cents: int                                  # final, after any discount
    currency: str = "USD"
    pricing_mode: str
    requires_approval: bool
    duration_minutes: int
    original_price_cents: Optional[int] = None        # pre-discount (None if no discount)
    discount_percent: int = 0


__all__ = [
    "BookingPricingMode",
    "CappeLocationHours",
    "CappeLocationCreate",
    "CappeLocationUpdate",
    "CappeLocation",
    "CappeStaffCreate",
    "CappeStaffUpdate",
    "CappeStaff",
    "CappeStaffImportError",
    "CappeStaffImportResult",
    "CappeBookingTypeCreate",
    "CappeBookingTypeUpdate",
    "CappeBookingType",
    "CappeRateRuleInput",
    "CappeRateRulesReplace",
    "CappeRateRule",
    "CappeRiderItemInput",
    "CappeRiderReplace",
    "CappeRiderItem",
    "CappeAvailabilitySlot",
    "CappeAvailabilityReplace",
    "CappeAvailability",
    "CappeBooking",
    "CappeBookingStatusUpdate",
    "CappeApprovalDecline",
    "CappeBookingRequest",
    "CappeBookingQuoteRequest",
    "CappeBookingReschedule",
    "CappeBookingQuote",
]
