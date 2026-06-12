"""Pydantic request/response shapes for Cappe."""
from datetime import datetime
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
