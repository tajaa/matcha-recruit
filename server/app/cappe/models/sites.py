"""Pydantic shapes — Cappe sites, pages, templates, readiness."""
import re
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from ._validators import MAX_SNAPSHOT_BYTES, assert_json_size

# Apex-domain shape (labels 1-63 chars, alnum/hyphen, real-looking TLD).
_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")


def _base_domain() -> str:
    """The configured Cappe base domain, lowercased and bare.

    Read at call time, not import time: models are imported before the app
    lifespan loads settings, and the env var is the same source config reads.
    """
    import os

    try:
        from ...config import get_settings

        base = get_settings().cappe_base_domain or ""
    except Exception:
        base = os.getenv("CAPPE_BASE_DOMAIN", "hey-matcha.com")
    return base.strip().lower().strip(".")


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
    # Our own hostnames are never connectable. `hey-matcha.com` is hardcoded
    # because it is where existing tenants live; the configured base domain is
    # read lazily, since on gummfit.com the apex (and every tenant subdomain
    # under it) would otherwise be claimable through the verify flow.
    blocked = {"hey-matcha.com", "localhost"}
    base = _base_domain()
    if base:
        blocked.add(base)
    for host in blocked:
        if v == host or v.endswith("." + host):
            raise ValueError("That domain can't be connected")
    return v


# --- Sites ------------------------------------------------------------------

class _SnapshotSizeLimit(BaseModel):
    """Bound the opaque page/theme JSON before anything renders or stores it.

    `content` / `theme_config` / `meta_config` are deliberately untyped — the
    block editor stores whatever the canvas produced — so nothing else caps
    them. The renderer walks every block synchronously on the request path.
    """

    @model_validator(mode="after")
    def _bounded_json(self):
        for field in ("content", "theme_config", "meta_config"):
            if field in type(self).model_fields:
                assert_json_size(field, getattr(self, field, None))
        return self


class CappeSiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: Literal["blank", "byo"] = "blank"
    # Set by the onboarding wizard: True when the business runs multiple
    # locations/branches. Drives whether the branch/location UI is surfaced.
    is_multi_location: bool = False


class CappeSiteFromTemplate(BaseModel):
    template_id: UUID
    name: Optional[str] = Field(default=None, max_length=255)


class CappeSiteUpdate(_SnapshotSizeLimit):
    name: Optional[str] = Field(default=None, max_length=255)
    # The tenant subdomain (<sub>.gummfit.com). Editable after creation; the
    # route slugifies + checks reserved/uniqueness before applying.
    subdomain: Optional[str] = Field(default=None, max_length=140)
    # custom_domain is NOT editable here — it's owned by the verified
    # connect/verify flow in routes/domains.py (a domain can't be claimed
    # without proving control of it via TXT record). See models/domains.py.
    status: Optional[Literal["draft", "published", "archived"]] = None
    theme_config: Optional[dict[str, Any]] = None
    meta_config: Optional[dict[str, Any]] = None
    timezone: Optional[str] = Field(default=None, max_length=64)
    is_multi_location: Optional[bool] = None
    tax_rate_bps: Optional[int] = Field(default=None, ge=0, le=10000)
    tax_label: Optional[str] = Field(default=None, max_length=40)
    shipping_flat_cents: Optional[int] = Field(default=None, ge=0)
    # Explicit null clears the threshold (model_fields_set gate in the route).
    shipping_free_threshold_cents: Optional[int] = Field(default=None, ge=0)
    shipping_label: Optional[str] = Field(default=None, max_length=40)
    # Reaches a Content-Disposition filename on both receipt routes, so it is
    # restricted to characters that can't break out of the quoted header value.
    receipt_prefix: Optional[str] = Field(
        default=None, max_length=12, pattern=r"^[A-Za-z0-9-]{1,12}$"
    )


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
    shipping_flat_cents: int = 0
    shipping_free_threshold_cents: Optional[int] = None
    shipping_label: str = "Shipping"
    receipt_prefix: Optional[str] = None
    # Discover directory. `listed` is the tenant's own opt-out; the platform-side
    # `directory_blocked` takedown is deliberately NOT exposed here — a suspended
    # listing must not be un-suspendable from the tenant's own settings page.
    listed: bool = True
    directory_category: Optional[str] = None
    directory_tags: list[str] = Field(default_factory=list)
    directory_blurb: Optional[str] = None
    directory_confirmed_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    page_count: Optional[int] = None


class CappeDirectoryListing(BaseModel):
    """The tenant's own view of how they appear in Discover."""
    listed: bool = True
    category: Optional[str] = None
    category_label: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    blurb: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    # False when the listing is incomplete — the directory's quality gate hides
    # a site with no category or blurb, and the UI must be able to say why
    # rather than leaving the tenant wondering where they are.
    visible: bool = False
    blocked: bool = False               # read-only; platform takedown
    categories: list[dict[str, str]] = Field(default_factory=list)   # the fixed taxonomy


class CappeDirectoryListingUpdate(BaseModel):
    """PATCH semantics: only fields actually sent are written, so a UI that
    edits the blurb alone can't blank the tags."""
    listed: Optional[bool] = None
    category: Optional[str] = Field(default=None, max_length=60)
    tags: Optional[list[str]] = None
    blurb: Optional[str] = Field(default=None, max_length=200)


# --- Pages ------------------------------------------------------------------

class CappePageCreate(_SnapshotSizeLimit):
    title: str = Field(min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    content: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    status: Literal["draft", "published", "archived"] = "draft"


class CappePageUpdate(_SnapshotSizeLimit):
    title: Optional[str] = Field(default=None, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    content: Optional[dict[str, Any]] = None
    sort_order: Optional[int] = None
    status: Optional[Literal["draft", "published", "archived"]] = None


class CappePagePreview(_SnapshotSizeLimit):
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
    "MAX_SNAPSHOT_BYTES",
    "normalize_custom_domain",
    "CappeSiteCreate",
    "CappeSiteFromTemplate",
    "CappeSiteUpdate",
    "CappeReadinessItem",
    "CappeReadiness",
    "CappeSite",
    "CappeDirectoryListing",
    "CappeDirectoryListingUpdate",
    "CappePageCreate",
    "CappePageUpdate",
    "CappePagePreview",
    "CappePage",
    "CappeTemplateSummary",
    "CappeTemplateDetail",
]
