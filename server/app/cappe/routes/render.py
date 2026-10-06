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
import json
import re
from html import escape

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ...core.services.redis_cache import cache_get, cache_set, check_rate_limit, client_ip, get_redis_cache
from ...database import get_connection
from ..models._validators import is_app_url_scheme
from ..services.booking_suggestion_access import canonical_suggestion_host
from ..services.commerce import release_abandoned_checkout
from ..services.common import normalize_host_header
from ..services.render import render_site_html
from ..services.render.account_page import render_account_page
from ..services.render.order_page import render_order_page
from ..services.render_cache import invalidate_site_render_cache
from ..services.stripe_connect import CappeStripeError
from ._shared import RESERVED_SUBDOMAINS, loads, loads_list

router = APIRouter()


_NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


async def _release_abandoned(order_token: str) -> None:
    """Hand back what an unpaid order was holding now that its buyer has left
    the payment page. Best-effort: if Stripe cannot be reached nothing is
    changed, the page still times out on its own, and the reaper is the
    backstop — not worth failing the buyer's return over."""
    try:
        await release_abandoned_checkout(order_token)
    except CappeStripeError:
        pass


def _local_path(value: str) -> str:
    """`value` if it is a path on this site, else the home page. Refuses
    anything a browser could read as another host (`//evil.test`, `/\\evil`)."""
    if (
        not value.startswith("/") or value.startswith("//")
        or "\\" in value or any(ord(ch) < 32 for ch in value)
    ):
        return "/"
    return value


@router.get("/__cappe/checkout-return")
async def checkout_return(request: Request, o: str = "", next: str = "/"):
    """Where Stripe sends a WEB buyer who backs out of the payment page.

    The order has been holding its stock and booking slots since it was
    created; nothing used to hand them back until the session timed out, so a
    buyer who clicked Back and tried again was told the item — the one THEY
    were holding — was out of stock. This closes the page, releases the order,
    and sends the buyer on to the page the storefront asked for. The token
    stops here: the redirect target never carries it."""
    if not re.fullmatch(r"[0-9a-f]{32}", o):
        raise HTTPException(400, "Invalid checkout return")
    async with get_connection() as conn:
        site = await _resolve_published_site(conn, request.headers.get("host"))
        if not site:
            raise HTTPException(404, "Site not found")
        mine = await conn.fetchval(
            "SELECT 1 FROM cappe_orders WHERE access_token=$1 AND site_id=$2", o, site["id"],
        )
    if mine:
        await _release_abandoned(o)
    return RedirectResponse(_local_path(next), status_code=302, headers=_NO_STORE)


@router.get("/__cappe/app-return")
async def app_return(request: Request, o: str = "", r: str = "success"):
    if not re.fullmatch(r"[0-9a-f]{32}", o) or r not in ("success", "cancel"):
        raise HTTPException(400, "Invalid checkout return")
    async with get_connection() as conn:
        site = await _resolve_published_site(conn, request.headers.get("host"))
        if not site:
            raise HTTPException(404, "Site not found")
        scheme = await conn.fetchval("SELECT app_url_scheme FROM cappe_sites WHERE id=$1", site["id"])
        exists = await conn.fetchval("SELECT id FROM cappe_orders WHERE access_token=$1 AND site_id=$2", o, site["id"])
        is_order = bool(exists)
        if not exists:
            exists = await conn.fetchval("SELECT id FROM cappe_shopper_subscriptions WHERE checkout_token=$1 AND site_id=$2", o, site["id"])
    if not exists:
        raise HTTPException(404, "Order not found")
    if is_order and r == "cancel":
        # Same release as the web return. A subscription checkout holds no
        # stock and has its own expiry path.
        await _release_abandoned(o)
    headers = _NO_STORE
    # Same rule as the write side (`CappeSiteUpdate`), re-checked here so a row
    # that predates the denylist can never become a web/script redirect.
    if is_app_url_scheme(scheme):
        return RedirectResponse(f"{scheme}://order/{o}?r={r}", status_code=302, headers=headers)
    return HTMLResponse("<!doctype html><html><body><h1>Return to the app</h1><p>You can close this window and check your order in the app.</p></body></html>", headers=headers)

# Labels that are never a tenant subdomain (brand / infra / auth hostnames on
# the shared apex). Centralized in _shared so site creation steers slugs away
# from the same set.
_RESERVED_SUBS = RESERVED_SUBDOMAINS

# Hosts that always belong to the main app — never looked up as custom domains.
# The configured base domain is folded in at call time (`_app_hosts`): with
# CAPPE_BASE_DOMAIN=gummfit.com the apex is not covered by the `.gummfit.com`
# suffix test below, so without this the brand apex itself resolves as a tenant
# custom domain — and `gummfit.com` becomes claimable through /domains/connect.
_STATIC_APP_HOSTS = frozenset(
    {"hey-matcha.com", "www.hey-matcha.com", "localhost", "127.0.0.1", "matcha-backend"}
)

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
    "media-src 'self' https:; "
    "connect-src 'self'; "
    # The map block embeds an OpenStreetMap iframe; without an explicit
    # frame-src it falls back to default-src 'self' and every published map
    # renders blank.
    "frame-src 'self' https://www.openstreetmap.org; "
    "frame-ancestors 'self'"
)


def tenant_security_headers() -> dict[str, str]:
    """Headers for tenant-rendered HTML (published pages + editor previews)."""
    return {
        "Cache-Control": "public, max-age=60",
        "Content-Security-Policy": TENANT_CSP,
        "X-Frame-Options": "SAMEORIGIN",
    }


def _base_domain() -> str:
    """Configured Cappe base domain, bare and lowercased.

    Resolved at call time: this module is imported before load_settings() runs
    in the app lifespan, so settings are preferred but the env var (the same
    source config reads) is the fallback.
    """
    try:
        from ...config import get_settings

        base = get_settings().cappe_base_domain or ""
    except Exception:
        base = os.getenv("CAPPE_BASE_DOMAIN", "hey-matcha.com")
    return base.strip().lower().strip(".")


def _prod_suffix() -> str:
    return "." + _base_domain()


def _app_hosts() -> frozenset[str]:
    base = _base_domain()
    if not base:
        return _STATIC_APP_HOSTS
    return _STATIC_APP_HOSTS | {base, f"www.{base}"}


def _norm_host(host: str | None) -> str | None:
    return normalize_host_header(host)


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
        or host in _app_hosts()
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
            "SELECT id, name, slug, subdomain, custom_domain, theme_config, meta_config FROM cappe_sites "
            "WHERE subdomain = $1 AND status = 'published'",
            sub,
        )
    candidates = _custom_domain_candidates(host)
    if not candidates:
        return None
    return await conn.fetchrow(
        "SELECT id, name, slug, subdomain, custom_domain, theme_config, meta_config FROM cappe_sites "
        "WHERE custom_domain = ANY($1::text[]) AND status = 'published'",
        candidates,
    )


async def invalidate_render_cache(site_id) -> None:
    """Drop cached rendered HTML for a site + reset the custom-domain host
    cache. Called by owner CRUD (site/page mutations, publish, delete).

    The Redis half now lives in `services/render_cache.py` so a services/
    caller (the setup concierge's chat-confirm path) can invalidate the
    rendered-HTML cache without importing routes/ — this wrapper stays the
    public name because `_host_cache` below is route-local state."""
    await invalidate_site_render_cache(site_id)
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

        loc_rows = await conn.fetch(
            "SELECT id, name, address, lat, lng, timezone, hours, contact_phone, contact_email "
            "FROM cappe_locations WHERE site_id = $1 AND active = true "
            "ORDER BY is_default DESC, sort_order, created_at",
            site["id"],
        )

    locations = [{**dict(r), "id": str(r["id"]), "hours": loads_list(r["hours"])} for r in loc_rows]
    nav = [{"slug": r["slug"], "title": r["title"]} for r in nav_rows]
    html = render_site_html(_site_dict(site), _page_dict(page), nav, locations=locations)
    if redis:
        await cache_set(redis, cache_key, html, ttl=_RENDER_TTL)
    return HTMLResponse(html, headers=tenant_security_headers())


@router.get("/", response_class=HTMLResponse)
async def render_home(request: Request):
    return await _render(request, None)


@router.get("/p/{page_slug}", response_class=HTMLResponse)
async def render_page(page_slug: str, request: Request):
    return await _render(request, page_slug)


async def _resolve_site_any_status(conn, host: str | None):
    """Host header → site row, published or not. Only for a page a buyer
    reaches with an order token: unpublishing a store must not take away the
    downloads and receipts its customers already paid for."""
    sub = subdomain_from_host(host)
    cols = "id, name, slug, subdomain, custom_domain, theme_config, meta_config, timezone, account_id"
    if sub:
        return await conn.fetchrow(f"SELECT {cols} FROM cappe_sites WHERE subdomain = $1", sub)
    candidates = _custom_domain_candidates(host)
    if not candidates:
        return None
    return await conn.fetchrow(f"SELECT {cols} FROM cappe_sites WHERE custom_domain = ANY($1::text[])", candidates)


_ORDER_PAGE_HEADERS = {
    "Cache-Control": "no-store",
    # The token is in the URL: no request from this page may carry it on.
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}


@router.get("/order/{token}", response_class=HTMLResponse)
async def order_page(token: str, request: Request):
    """The buyer's order page on the store's own host — see
    `services/render/order_page.py`. Resolved by the order's unguessable token
    AND the host: one store's host never shows another store's order."""
    host = request.headers.get("host")
    if subdomain_from_host(host) is None and not _custom_domain_candidates(host):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        return _not_found_html("Order not found")
    await check_rate_limit(client_ip(request), "cappe_order_page", 30, 60)
    async with get_connection() as conn:
        site = await _resolve_site_any_status(conn, host)
        if site is None:
            return _not_found_html("Site not found")
        order = await conn.fetchrow(
            """SELECT o.id, o.status, o.requires_approval, o.approved_at, o.pay_by, o.decline_reason,
                      o.subtotal_cents, o.tax_cents, o.shipping_cents, o.total_cents, o.refunded_cents,
                      o.promo_code, o.discount_cents,
                      o.currency, o.carrier, o.tracking_number, o.shipping_address, o.receipt_number,
                      o.stripe_session_id, s.tax_label, s.shipping_label
                 FROM cappe_orders o JOIN cappe_sites s ON s.id = o.site_id
                WHERE o.access_token = $1 AND o.site_id = $2""",
            token, site["id"],
        )
        if order is None:
            return _not_found_html("Order not found")
        items = await conn.fetch(
            """SELECT oi.title, oi.quantity, oi.fulfillment, oi.unit_price_cents, oi.selected_options,
                      oi.deliverable_url, p.digital_file_url, b.starts_at AS booking_starts_at
                 FROM cappe_order_items oi
                 LEFT JOIN cappe_products p ON p.id = oi.product_id
                 LEFT JOIN cappe_bookings b ON b.id = oi.booking_id
                WHERE oi.order_id = $1 ORDER BY oi.created_at""",
            order["id"],
        )
        owner = await conn.fetchrow(
            "SELECT stripe_account_id, stripe_charges_enabled, status FROM cappe_accounts WHERE id = $1",
            site["account_id"],
        )
        nav_rows = await conn.fetch(
            "SELECT title, slug FROM cappe_pages WHERE site_id = $1 AND status = 'published' "
            "ORDER BY sort_order, created_at",
            site["id"],
        )
        now = await conn.fetchval("SELECT NOW()")
    takes_cards = bool(owner and owner["stripe_account_id"] and owner["stripe_charges_enabled"]
                       and (owner["status"] or "active") == "active")
    order_ctx = {
        **dict(order),
        "shipping_address": loads(order["shipping_address"]) or None,
        "site_name": site["name"], "timezone": site["timezone"],
    }
    item_ctx = [{
        **dict(it),
        "selected_options": loads_list(it["selected_options"]),
        "download_url": it["digital_file_url"] if it["fulfillment"] == "digital" else None,
    } for it in items]
    html = render_order_page(
        {**_site_dict(site), "timezone": site["timezone"]},
        [{"slug": r["slug"], "title": r["title"]} for r in nav_rows],
        order_ctx, item_ctx, token=token, takes_cards=takes_cards, now=now,
        clear_cart=order["status"] not in ("cancelled", "declined"),
    )
    return HTMLResponse(html, headers={**tenant_security_headers(), **_ORDER_PAGE_HEADERS})


@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    """The shopper's account page on the store's own host — see
    `services/render/account_page.py`. Renders for an unpublished store too: a
    shopper must still be able to cancel what they subscribed to."""
    host = request.headers.get("host")
    if subdomain_from_host(host) is None and not _custom_domain_candidates(host):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await check_rate_limit(client_ip(request), "cappe_account_page", 60, 60)
    async with get_connection() as conn:
        site = await _resolve_site_any_status(conn, host)
        if site is None:
            return _not_found_html("Site not found")
        nav_rows = await conn.fetch(
            "SELECT title, slug FROM cappe_pages WHERE site_id = $1 AND status = 'published' "
            "ORDER BY sort_order, created_at",
            site["id"],
        )
    html = render_account_page(
        {**_site_dict(site), "timezone": site["timezone"]},
        [{"slug": r["slug"], "title": r["title"]} for r in nav_rows],
    )
    return HTMLResponse(html, headers={**tenant_security_headers(), **_ORDER_PAGE_HEADERS})


@router.get("/__cappe/booking-suggestions/access", response_class=HTMLResponse)
async def booking_suggestion_access_page(request: Request):
    """Redeem a fragment token on the tenant host, then return to the site."""
    host = request.headers.get("host")
    if subdomain_from_host(host) is None and not _custom_domain_candidates(host):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    async with get_connection() as conn:
        site = await _resolve_published_site(conn, host)
    if site is None:
        return _not_found_html("Site not found")
    normalized_host = _norm_host(host)
    canonical_host = canonical_suggestion_host(site)
    local_hosts = {
        f"{site['subdomain']}.localhost",
        f"{site['subdomain']}.cappe.localhost",
    }
    if normalized_host not in {canonical_host, *local_hosts}:
        return _not_found_html("Booking access is available on the tenant host")
    slug = json.dumps(site["slug"])
    safe_name = escape(site["name"] or "Booking")
    title = escape(f"Booking access | {site['name']}")
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0b0d;color:#e4e4e7;font:16px system-ui,sans-serif}}main{{max-width:32rem;padding:2rem;text-align:center}}p{{color:#a1a1aa;line-height:1.6}}a{{color:#c6f16b}}</style>
</head><body><main><h1>Opening booking access...</h1><p id="message">Checking your secure link.</p><a id="back" href="/" hidden>Return to {safe_name}</a></main>
<script>(function(){{
var msg=document.getElementById('message'),back=document.getElementById('back'),token=window.location.hash.slice(1),slug={slug};
function fail(text){{msg.textContent=text;back.hidden=false;}}
window.history.replaceState(null,'',window.location.pathname+window.location.search);
if(!token){{fail('This access link is missing its token.');return;}}
fetch('/api/cappe/public/sites/'+encodeURIComponent(slug)+'/booking-suggestions/access/redeem',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token:token}})}})
 .then(function(r){{if(!r.ok)throw new Error('expired');return r.json();}})
 .then(function(){{window.location.replace('/#book');}})
 .catch(function(){{fail('This access link is invalid or has expired.');}});
}})();</script></body></html>""",
        headers={**tenant_security_headers(), "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
