"""Gallery previews — a template rendered as a browsable, standalone page.

The gallery shows each template as a scaled live render, and the "Preview"
modal lets a person walk every page before choosing. Both hit
`GET /templates/{slug}/preview?page=…`, which this module renders:

- `preview=True` so widgets (store / booking / newsletter / reviews) draw
  their static placeholder instead of calling the public API for a site that
  does not exist.
- Internal links are rewritten to `?page=<slug>` so clicking "View menu" in
  the preview opens the template's menu page inside the same iframe rather
  than a 404 on the API host.
- `premium` chooses the layer: a free account previews exactly what its clone
  will keep; a paid account sees the polish it will get. Deciding that is the
  caller's job (the gallery passes the signed-in plan); this stays pure.

Rendering is memoised per (slug, page, premium). The registry is static for
the life of the process, so the cache never needs invalidating, and the
gallery's N cards cost N dict lookups instead of N full renders — the old
per-card render at 30/min/IP is what made a bigger catalog 429. Only REAL
(template, page) pairs ever reach the cache: the lookup is validated first, so
a scraper's junk slugs cannot evict the pages the gallery actually serves.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from ..design_gate import gate_content, gate_theme
from ..render import render_site_html
from . import get_template
from ._shared import substitute_tokens

# Plans the gate treats as premium — the preview takes a bool so it never has
# to know plan names; the route maps the account's plan onto it.
_FREE_PLAN = "free"
_PREMIUM_PLAN = "business"

_PAGE_HREF_RE = re.compile(r'href="/p/([a-z0-9-]+)"')
_HOME_HREF_RE = re.compile(r'href="/"')


def _rewrite_links(html: str, *, premium: bool) -> str:
    suffix = "&premium=1" if premium else ""
    html = _PAGE_HREF_RE.sub(lambda m: f'href="?page={m.group(1)}{suffix}"', html)
    return _HOME_HREF_RE.sub(f'href="?page=home{suffix}"', html)


def render_template_preview(slug: str, page_slug: str = "home", premium: bool = False) -> Optional[str]:
    """Standalone HTML for one page of a template, or None if either the
    template or the page does not exist. Misses never touch the cache."""
    t = get_template(slug)
    if t is None or t.page(page_slug or "home") is None:
        return None
    return _render_cached(t.slug, page_slug or "home", bool(premium))


# Bounded by the catalog: templates × pages × 2 layers, all validated above.
@lru_cache(maxsize=512)
def _render_cached(slug: str, page_slug: str, premium: bool) -> str:
    t = get_template(slug)
    page = t.page(page_slug)
    plan = _PREMIUM_PLAN if premium else _FREE_PLAN
    values = {"business_name": t.sample_name}
    site = {
        "name": t.sample_name,
        "theme_config": gate_theme(t.theme, plan),
        "meta_config": {},
    }
    content = gate_content(substitute_tokens(page.get("content") or {}, values), plan)
    html = render_site_html(
        site,
        {"title": page.get("title"), "slug": page.get("slug"), "content": content},
        t.nav,
        preview=True,
    )
    return _rewrite_links(html, premium=premium)
