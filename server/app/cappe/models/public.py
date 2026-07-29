"""Pydantic shapes — public-facing render/booking/thread/review views."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .engage import CappeMessage
from .sites import CappePage

class CappePublicSite(BaseModel):
    name: str
    slug: str
    theme_config: dict[str, Any] = Field(default_factory=dict)
    meta_config: dict[str, Any] = Field(default_factory=dict)
    pages: list[CappePage] = Field(default_factory=list)


class CappePublicLocation(BaseModel):
    """A location as exposed to the public booking widget / map / hours."""
    id: UUID
    name: str
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    timezone: Optional[str] = None
    hours: list[dict[str, Any]] = Field(default_factory=list)
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None


class CappePublicStaff(BaseModel):
    """A bookable staff member as shown in the public booking widget."""
    id: UUID
    name: str
    bio: Optional[str] = None
    image_url: Optional[str] = None


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


# Public (token-resolved) thread view for the client.
class CappePublicThread(BaseModel):
    site_name: str
    subject: Optional[str] = None
    messages: list[CappeMessage] = Field(default_factory=list)


class CappePublicReview(BaseModel):
    """Approved review as shown on the public site."""
    author_name: str
    rating: Optional[int] = None
    body: str
    created_at: datetime


# --- Discover directory ------------------------------------------------------

class CappeDirectoryEntry(BaseModel):
    """One directory card.

    This shape IS the public allowlist for the whole tenant base — the directory
    is the one endpoint that returns many sites at once, so every field here is
    published for every listed business simultaneously. Deliberately absent:
    contact email (a one-request spam harvest), account id, plan, and anything
    else from `cappe_accounts` beyond the business/personal badge.
    """
    slug: str
    name: str
    url: str                                  # the site's own public address
    category: Optional[str] = None
    category_label: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    blurb: Optional[str] = None
    logo_url: Optional[str] = None
    account_type: str = "business"            # business | personal (card badge)
    city: Optional[str] = None
    region: Optional[str] = None
    distance_km: Optional[float] = None       # only when the caller sent lat/lng
    rating: Optional[float] = None            # shown, never sorted on — see the route
    review_count: int = 0
    published_at: Optional[datetime] = None


class CappeDirectoryPage(BaseModel):
    entries: list[CappeDirectoryEntry] = Field(default_factory=list)
    # Clamped to the route's anti-enumeration depth cap, so this is "results you
    # can reach", not "sites we have".
    total: int = 0
    next_offset: Optional[int] = None         # None = no more reachable results


class CappeDirectoryCategory(BaseModel):
    slug: str
    label: str
    count: int = 0


class CappeDirectoryCategories(BaseModel):
    categories: list[CappeDirectoryCategory] = Field(default_factory=list)
    total: int = 0


__all__ = [
    "CappePublicSite",
    "CappePublicLocation",
    "CappePublicStaff",
    "CappePublicBooking",
    "CappePublicThread",
    "CappePublicReview",
    "CappeDirectoryEntry",
    "CappeDirectoryPage",
    "CappeDirectoryCategory",
    "CappeDirectoryCategories",
]
