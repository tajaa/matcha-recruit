"""Pydantic shapes — Cappe sites, pages, templates, readiness."""
import re
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

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


# --- Sites ------------------------------------------------------------------

class CappeSiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: Literal["blank", "byo"] = "blank"
    custom_domain: Optional[str] = Field(default=None, max_length=255)
    # Set by the onboarding wizard: True when the business runs multiple
    # locations/branches. Drives whether the branch/location UI is surfaced.
    is_multi_location: bool = False

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
    is_multi_location: Optional[bool] = None
    tax_rate_bps: Optional[int] = Field(default=None, ge=0, le=10000)
    tax_label: Optional[str] = Field(default=None, max_length=40)
    receipt_prefix: Optional[str] = Field(default=None, max_length=12)


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
    is_multi_location: bool = False
    tax_rate_bps: int = 0
    tax_label: str = "Tax"
    receipt_prefix: Optional[str] = None
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
    # Unsaved meta_config (e.g. live promos editing) — when omitted, saved meta used.
    meta_config: Optional[dict[str, Any]] = None
    # When true, render with the canvas selection/edit runtime (Business editor).
    editable: bool = False


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


__all__ = [
    "normalize_custom_domain",
    "CappeSiteCreate",
    "CappeSiteFromTemplate",
    "CappeSiteUpdate",
    "CappeReadinessItem",
    "CappeReadiness",
    "CappeSite",
    "CappePageCreate",
    "CappePageUpdate",
    "CappePagePreview",
    "CappePage",
    "CappeTemplateSummary",
    "CappeTemplateDetail",
]
