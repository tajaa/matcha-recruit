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


__all__ = [
    "CappePublicSite",
    "CappePublicLocation",
    "CappePublicStaff",
    "CappePublicBooking",
    "CappePublicThread",
    "CappePublicReview",
]
