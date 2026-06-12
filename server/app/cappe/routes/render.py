"""Host-routed public Cappe site renderer (served at the site's subdomain).

Mounted at root (no /api prefix). Every handler is gated on the request Host
resolving to a Cappe subdomain — `<sub>.cappe.hey-matcha.com` in prod, or
`<sub>.cappe.localhost` / `<sub>.localhost` for local testing. Non-Cappe hosts
get a 404 so normal API/root routes are unaffected.
"""
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from ...database import get_connection
from ..services.render import render_site_html
from ._shared import loads

router = APIRouter()

# Labels that are never a tenant subdomain.
_RESERVED_SUBS = {"www", "app", "api", "admin", "cappe", "mail", "ftp"}


def subdomain_from_host(host: str | None) -> str | None:
    """Extract the tenant subdomain from a Host header, or None.

    Accepts `<sub>.cappe.<domain>` (prod) and `<sub>.cappe.localhost` /
    `<sub>.localhost` (local). Strips the port.
    """
    if not host:
        return None
    host = host.split(":", 1)[0].strip().lower().rstrip(".")
    if not host or "." not in host:
        return None
    parts = host.split(".")
    sub = None
    if host.endswith(".cappe.localhost") or host.endswith(".cappe.hey-matcha.com"):
        sub = parts[0]
    elif host.endswith(".localhost") and len(parts) == 2 and parts[0] != "localhost":
        # convenience: <sub>.localhost
        sub = parts[0]
    if sub and sub not in _RESERVED_SUBS:
        return sub
    return None


async def _load_published_site(conn, subdomain: str):
    site = await conn.fetchrow(
        "SELECT id, name, theme_config FROM cappe_sites "
        "WHERE subdomain = $1 AND status = 'published'",
        subdomain,
    )
    if site is None:
        return None, []
    pages = await conn.fetch(
        "SELECT id, title, slug, content FROM cappe_pages "
        "WHERE site_id = $1 AND status = 'published' ORDER BY sort_order, created_at",
        site["id"],
    )
    return site, pages


def _site_dict(site) -> dict:
    return {"name": site["name"], "theme_config": loads(site["theme_config"])}


def _page_dict(page) -> dict:
    return {"title": page["title"], "slug": page["slug"], "content": loads(page["content"])}


def _nav(pages) -> list[dict]:
    return [{"slug": p["slug"], "title": p["title"]} for p in pages]


def _not_found_html(message: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><body style='font-family:system-ui;text-align:center;padding:6rem'>"
        f"<h1 style='color:#71717a'>{message}</h1></body></html>",
        status_code=status.HTTP_404_NOT_FOUND,
    )


@router.get("/", response_class=HTMLResponse)
async def render_home(request: Request):
    sub = subdomain_from_host(request.headers.get("host"))
    if not sub:
        # Not a tenant host — let nothing else here handle it.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    async with get_connection() as conn:
        site, pages = await _load_published_site(conn, sub)
    if site is None or not pages:
        return _not_found_html("Site not found")
    # Home = a page slugged 'home', else the first.
    home = next((p for p in pages if p["slug"] == "home"), pages[0])
    return HTMLResponse(render_site_html(_site_dict(site), _page_dict(home), _nav(pages)))


@router.get("/p/{page_slug}", response_class=HTMLResponse)
async def render_page(page_slug: str, request: Request):
    sub = subdomain_from_host(request.headers.get("host"))
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    async with get_connection() as conn:
        site, pages = await _load_published_site(conn, sub)
    if site is None:
        return _not_found_html("Site not found")
    page = next((p for p in pages if p["slug"] == page_slug), None)
    if page is None:
        return _not_found_html("Page not found")
    return HTMLResponse(render_site_html(_site_dict(site), _page_dict(page), _nav(pages)))
