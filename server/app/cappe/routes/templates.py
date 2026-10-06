"""Cappe template catalog — public, read-only, served from the code registry.

`services/site_templates` is the source of truth (see its docstring for why
the `cappe_templates` table was retired). Three endpoints:

- `GET /templates[?category=]` — gallery cards.
- `GET /templates/{slug}/preview?page=&premium=` — one page of a template as
  a standalone, browsable HTML document (memoised in the service).
- `GET /templates/categories` — the fixed Discover taxonomy, no counts, no DB.
- `GET /templates/placeholder/{key}.svg` — the self-hosted stand-in a template
  image slot shows until `scripts/cappe_template_imagery.py` has generated the
  real photo; after that it REDIRECTS to the photo, so sites cloned early pick
  the imagery up on their own.

All public, all rate-limited: these are the only unauthenticated routes that
render anything, and the gallery fans out to one request per card.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ...core.services.redis_cache import check_rate_limit, client_ip
from ..models.cappe import CappeTemplateSummary
from ..services.directory import CATEGORY_SLUGS, category_options
from ..services.site_templates import list_templates as _list_templates
from ..services.site_templates import template_summary
from ..services.site_templates.imagery import (
    IMAGE_MANIFEST,
    IMAGE_URLS,
    PLACEHOLDER_ROUTE,
    placeholder_svg,
)
from ..services.site_templates.preview import render_template_preview
from .render import tenant_security_headers

router = APIRouter()

# Memoised render → each hit is a dict lookup, so the limit only has to stop a
# scraper, not protect CPU. 17 cards × a couple of reloads must never 429.
_PREVIEW_LIMIT_PER_MIN = 240
# One placeholder per image slot per card; a gallery load is ~80 of these.
_PLACEHOLDER_LIMIT_PER_MIN = 600


@router.get("/templates", response_model=list[CappeTemplateSummary])
async def list_templates(category: str | None = Query(default=None, max_length=60)):
    """Every template, optionally one Discover category's worth."""
    if category and category not in CATEGORY_SLUGS:
        return []
    return [template_summary(t) for t in _list_templates(category)]


@router.get("/templates/{slug}/preview", response_class=HTMLResponse)
async def preview_template(
    slug: str,
    request: Request,
    page: str = Query(default="home", max_length=160, pattern=r"^[a-z0-9-]*$"),
    premium: bool = Query(default=False),
):
    """Render one page of a template as standalone HTML for the gallery card
    and the full-site preview modal. `premium` shows the polish a paid plan
    keeps; the gallery passes the signed-in account's tier."""
    await check_rate_limit(client_ip(request), "cappe_tpl_preview", _PREVIEW_LIMIT_PER_MIN, 60)
    html = render_template_preview(slug, page or "home", premium)
    if html is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    # The preview exists to be FRAMED (gallery card + preview modal) and ships
    # inline widget scripts + Google Fonts. Without a handler-set policy the
    # app-wide middleware (main.py:add_security_headers) applies the strict
    # default — frame-ancestors 'none', X-Frame-Options DENY, script-src 'self'
    # — and every browser refuses to draw it. Same tenant policy the editor's
    # own preview iframe uses.
    return HTMLResponse(html, headers={**tenant_security_headers(), "Cache-Control": "public, max-age=300"})


@router.get("/templates/categories")
async def template_categories() -> list[dict[str, str]]:
    """The fixed Discover taxonomy as `[{slug, label}]`.

    The onboarding wizard's "what kind of business?" chips. The public
    directory's own categories endpoint also answers this, but it COUNTS listed
    sites on every call and shares the directory's rate limit — work and
    contention the wizard has no use for. This is a constant.
    """
    return category_options()


# Short on purpose: this URL's answer CHANGES the day the slot's photo is
# generated (tile → redirect), and sites cloned before that day hold this URL
# for good. An `immutable` day-long cache would pin them to the tile.
_PLACEHOLDER_CACHE = "public, max-age=3600"


@router.get(PLACEHOLDER_ROUTE)
async def template_placeholder(key: str, request: Request):
    """Artwork for a template image slot. Before the slot's photo exists: a
    deterministic gradient tile. After: a redirect to the hosted photo, so a
    site that was cloned early (and so stored this path) shows the real image
    without anyone rewriting its pages. Only manifest keys resolve, so this
    can't be used as a free image generator for arbitrary strings."""
    if key not in IMAGE_MANIFEST:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown image")
    await check_rate_limit(client_ip(request), "cappe_tpl_placeholder", _PLACEHOLDER_LIMIT_PER_MIN, 60)
    hosted = IMAGE_URLS.get(key)
    if hosted:
        return RedirectResponse(hosted, status_code=status.HTTP_302_FOUND, headers={"Cache-Control": _PLACEHOLDER_CACHE})
    return Response(
        content=placeholder_svg(key),
        media_type="image/svg+xml",
        headers={"Cache-Control": _PLACEHOLDER_CACHE},
    )
