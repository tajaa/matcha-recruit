"""Host-routed public Cappe site renderer (served at the site's subdomain or
a connected custom domain).

Mounted at root (no /api prefix). Every handler is gated on the request Host
resolving to a Cappe site — `<sub>.hey-matcha.com` in prod (MVP reuses the main
apex; base domain configurable via CAPPE_BASE_DOMAIN), `<sub>.cappe.localhost` /
`<sub>.localhost` for local testing, or a site's `custom_domain`. The main app
keeps the apex + `www` (and other reserved labels — see RESERVED_SUBDOMAINS);
non-Cappe hosts get a 404 so normal API/root routes are unaffected.

Rendered HTML is cached in Redis per (site, page) and invalidated by the owner
CRUD routes via `invalidate_render_cache` — page views cost one indexed site
lookup + a Redis GET on the hot path.
"""
import os
import time

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from ...core.services.redis_cache import (
    cache_delete_pattern,
    cache_get,
    cache_set,
    get_redis_cache,
)
from ...database import get_connection
from ..services.render import render_site_html
from ._shared import RESERVED_SUBDOMAINS, loads

router = APIRouter()

# Labels that are never a tenant subdomain (brand / infra / auth hostnames on
# the shared apex). Centralized in _shared so site creation steers slugs away
# from the same set.
_RESERVED_SUBS = RESERVED_SUBDOMAINS

# Hosts that always belong to the main app — never looked up as custom domains.
_APP_HOSTS = {"hey-matcha.com", "www.hey-matcha.com", "localhost", "127.0.0.1", "matcha-backend"}

_RENDER_TTL = 300  # seconds; owner mutations invalidate explicitly

# CSP for published Cappe pages: they ship inline widget scripts + Google Fonts
# (all user content is HTML-escaped + URL-sanitized by services/render.py). The
# app-wide security middleware applies the strict policy only when a response
# doesn't already carry one, so setting it here is what opts these pages out.
TENANT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-ancestors 'self'"
)


def tenant_security_headers() -> dict[str, str]:
    """Headers for tenant-rendered HTML (published pages + editor previews)."""
    return {
        "Cache-Control": "public, max-age=60",
        "Content-Security-Policy": TENANT_CSP,
        "X-Frame-Options": "SAMEORIGIN",
    }


# Read from env directly (mirrors settings.cappe_base_domain): this module is
# imported before load_settings() runs in the app lifespan.
_PROD_SUFFIX = "." + os.getenv("CAPPE_BASE_DOMAIN", "hey-matcha.com")


def _prod_suffix() -> str:
    return _PROD_SUFFIX


def _norm_host(host: str | None) -> str | None:
    if not host:
        return None
    host = host.split(":", 1)[0].strip().lower().rstrip(".")
    return host or None


def subdomain_from_host(host: str | None) -> str | None:
    """Extract the tenant subdomain from a Host header, or None.

    Accepts `<sub>.<cappe_base_domain>` (prod) and `<sub>.cappe.localhost` /
    `<sub>.localhost` (local). Strips the port.
    """
    host = _norm_host(host)
    if not host or "." not in host:
        return None
    parts = host.split(".")
    sub = None
    if host.endswith(".cappe.localhost") or host.endswith(_prod_suffix()):
        sub = parts[0]
    elif host.endswith(".localhost") and len(parts) == 2 and parts[0] != "localhost":
        # convenience: <sub>.localhost
        sub = parts[0]
    if sub and sub not in _RESERVED_SUBS:
        return sub
    return None


def _custom_domain_candidates(host: str | None) -> list[str]:
    """Hostnames to match against cappe_sites.custom_domain (apex stored;
    `www.` accepted at request time). Empty when the host can't be a tenant."""
    host = _norm_host(host)
    if (
        not host
        or "." not in host
        or host in _APP_HOSTS
        or host.endswith(".localhost")
        or host.endswith(_prod_suffix())
    ):
        return []
    if host.startswith("www."):
        return [host, host[4:]]
    return [host]


# --- Trusted-host support (consumed by main.py middleware) -------------------
# Custom domains can't be enumerated in a static allowlist, so the host gate
# falls back to "is this a registered custom domain?" with a short-TTL
# in-process cache (bounded so host-header spam can't grow it unboundedly).

_host_cache: dict[str, tuple[float, bool]] = {}
_HOST_CACHE_TTL = 60.0
_HOST_CACHE_MAX = 4096


async def is_registered_custom_domain(host: str | None) -> bool:
    candidates = _custom_domain_candidates(host)
    if not candidates:
        return False
    key = candidates[0]
    now = time.monotonic()
    hit = _host_cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    try:
        async with get_connection() as conn:
            found = await conn.fetchval(
                "SELECT 1 FROM cappe_sites WHERE custom_domain = ANY($1::text[])",
                candidates,
            )
    except Exception:
        return False
    if len(_host_cache) >= _HOST_CACHE_MAX:
        _host_cache.clear()
    _host_cache[key] = (now + _HOST_CACHE_TTL, found is not None)
    return found is not None


# --- Site resolution + rendering ---------------------------------------------

async def _resolve_published_site(conn, host: str | None):
    """Host header → published site row, by subdomain or custom domain."""
    sub = subdomain_from_host(host)
    if sub:
        return await conn.fetchrow(
            "SELECT id, name, slug, theme_config, meta_config FROM cappe_sites "
            "WHERE subdomain = $1 AND status = 'published'",
            sub,
        )
    candidates = _custom_domain_candidates(host)
    if not candidates:
        return None
    return await conn.fetchrow(
        "SELECT id, name, slug, theme_config, meta_config FROM cappe_sites "
        "WHERE custom_domain = ANY($1::text[]) AND status = 'published'",
        candidates,
    )


async def invalidate_render_cache(site_id) -> None:
    """Drop cached rendered HTML for a site + reset the custom-domain host
    cache. Called by owner CRUD (site/page mutations, publish, delete)."""
    redis = get_redis_cache()
    if redis:
        await cache_delete_pattern(redis, f"cappe:render:{site_id}:")
    _host_cache.clear()


def _site_dict(site) -> dict:
    return {
        "name": site["name"],
        "slug": site["slug"],
        "theme_config": loads(site["theme_config"]),
        "meta_config": loads(site["meta_config"]),
    }


def _page_dict(page) -> dict:
    return {"title": page["title"], "slug": page["slug"], "content": loads(page["content"])}


def _not_found_html(message: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><body style='font-family:system-ui;text-align:center;padding:6rem'>"
        f"<h1 style='color:#71717a'>{message}</h1></body></html>",
        status_code=status.HTTP_404_NOT_FOUND,
    )


async def _render(request: Request, page_slug: str | None) -> HTMLResponse:
    host = request.headers.get("host")
    if subdomain_from_host(host) is None and not _custom_domain_candidates(host):
        # Not a tenant-shaped host (e.g. the app's own domain) — fall through
        # to normal 404 handling without touching the DB.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    redis = get_redis_cache()
    async with get_connection() as conn:
        site = await _resolve_published_site(conn, host)
        if site is None:
            return _not_found_html("Site not found")

        cache_key = f"cappe:render:{site['id']}:{page_slug or '__home__'}"
        if redis:
            cached = await cache_get(redis, cache_key)
            if isinstance(cached, str):
                return HTMLResponse(cached, headers=tenant_security_headers())

        nav_rows = await conn.fetch(
            "SELECT title, slug FROM cappe_pages "
            "WHERE site_id = $1 AND status = 'published' ORDER BY sort_order, created_at",
            site["id"],
        )
        if not nav_rows:
            return _not_found_html("Site not found")

        if page_slug is None:
            # Home = a page slugged 'home', else the first.
            target = next((r["slug"] for r in nav_rows if r["slug"] == "home"), nav_rows[0]["slug"])
        elif any(r["slug"] == page_slug for r in nav_rows):
            target = page_slug
        else:
            return _not_found_html("Page not found")

        page = await conn.fetchrow(
            "SELECT title, slug, content FROM cappe_pages "
            "WHERE site_id = $1 AND slug = $2 AND status = 'published'",
            site["id"], target,
        )
        if page is None:
            return _not_found_html("Page not found")

    nav = [{"slug": r["slug"], "title": r["title"]} for r in nav_rows]
    html = render_site_html(_site_dict(site), _page_dict(page), nav)
    if redis:
        await cache_set(redis, cache_key, html, ttl=_RENDER_TTL)
    return HTMLResponse(html, headers=tenant_security_headers())


@router.get("/", response_class=HTMLResponse)
async def render_home(request: Request):
    return await _render(request, None)


@router.get("/p/{page_slug}", response_class=HTMLResponse)
async def render_page(page_slug: str, request: Request):
    return await _render(request, page_slug)
