"""Pydantic shapes — Cappe engagement (newsletter/campaigns, forms, reviews,
messages/threads, clients, blog)."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

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


# ===========================================================================
# Clients (derived directory of people who've interacted with a site)
# ===========================================================================

class CappeClient(BaseModel):
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    orders_count: int = 0
    bookings_count: int = 0
    is_subscriber: bool = False
    has_thread: bool = False
    is_imported: bool = False           # has a row in cappe_clients (manual/CSV)
    total_spent_cents: int = 0
    last_activity: Optional[datetime] = None
    # Branch the client belongs to (explicit on import, else latest booking's).
    location_id: Optional[UUID] = None
    location_name: Optional[str] = None


class CappeClientCreate(BaseModel):
    """Add/update a single managed client (upsert by email within the site)."""
    email: str = Field(min_length=3, max_length=320)
    name: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=40)
    location_id: Optional[UUID] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None  # None = leave unchanged (no absent-vs-clear signal needed today)
    add_to_newsletter: bool = False


class CappeClientImportError(BaseModel):
    row: int                            # 1-based data row (header excluded)
    email: Optional[str] = None
    reason: str


class CappeClientImportResult(BaseModel):
    total: int = 0                      # data rows seen
    created: int = 0
    updated: int = 0
    skipped: int = 0
    newsletter_added: int = 0
    branches_matched: int = 0           # rows that resolved a branch by name
    errors: list[CappeClientImportError] = Field(default_factory=list)


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


__all__ = [
    "CappeSubscriberCreate",
    "CappeSubscriber",
    "CappeSubscribeRequest",
    "CappeCampaignCreate",
    "CappeCampaignUpdate",
    "CappeCampaign",
    "CappeFormField",
    "CappeFormCreate",
    "CappeFormUpdate",
    "CappeForm",
    "CappeFormSubmission",
    "CappeFormSubmitRequest",
    "CappeMessage",
    "CappeThread",
    "CappeThreadDetail",
    "CappeThreadCreate",
    "CappeMessageCreate",
    "CappeClient",
    "CappeClientCreate",
    "CappeClientImportError",
    "CappeClientImportResult",
    "CappePostCreate",
    "CappePostUpdate",
    "CappePost",
    "CappeReviewCreate",
    "CappeReviewModerate",
    "CappeReview",
]
