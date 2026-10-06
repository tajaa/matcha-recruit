"""Cappe template catalog — public, read-only, served from the code registry.

`services/site_templates` is the source of truth (see its docstring for why
the `cappe_templates` table was retired). Three endpoints:

- `GET /templates[?category=]` — gallery cards.
- `GET /templates/{slug}/preview?page=&premium=` — one page of a template as
  a standalone, browsable HTML document (memoised in the service).
- `GET /templates/placeholder/{key}.svg` — the self-hosted stand-in a template
  image slot shows until `scripts/cappe_template_imagery.py` has generated the
  real photo. Deterministic per key, so the same slot always draws the same
  tile and the browser can cache it hard.

All public, all rate-limited: these are the only unauthenticated routes that
render anything, and the gallery fans out to one request per card.
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse

from ...core.services.redis_cache import check_rate_limit, client_ip
from ..models.cappe import CappeTemplateSummary
from ..services.directory import CATEGORY_SLUGS
from ..services.site_templates import list_templates as _list_templates
from ..services.site_templates import template_summary
from ..services.site_templates.imagery import IMAGE_MANIFEST
from ..services.site_templates.preview import render_template_preview

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
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=300"})


def _placeholder_svg(key: str) -> str:
    """A soft two-tone gradient tile keyed on the slot name: deterministic,
    brand-neutral, no text. Hue from the key's hash; saturation and lightness
    kept low so it reads as 'photo to come', not as part of the palette."""
    h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    hue_a = h % 360
    hue_b = (hue_a + 28) % 360
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800" width="1200" height="800" '
        'role="img" aria-label="Placeholder image">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="hsl({hue_a} 22% 62%)"/>'
        f'<stop offset="1" stop-color="hsl({hue_b} 26% 42%)"/></linearGradient>'
        '<radialGradient id="r" cx="0.75" cy="0.2" r="0.8">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0.28"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>'
        '<rect width="1200" height="800" fill="url(#g)"/>'
        '<rect width="1200" height="800" fill="url(#r)"/>'
        '</svg>'
    )


@router.get("/templates/placeholder/{key}.svg")
async def template_placeholder(key: str, request: Request):
    """Stand-in artwork for a template image slot that has no generated photo
    yet. Only manifest keys resolve, so this can't be used as a free image
    generator for arbitrary strings."""
    if key not in IMAGE_MANIFEST:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown image")
    await check_rate_limit(client_ip(request), "cappe_tpl_placeholder", _PLACEHOLDER_LIMIT_PER_MIN, 60)
    return Response(
        content=_placeholder_svg(key),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
