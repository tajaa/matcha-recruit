"""Public email verification for existing-client AI booking suggestions."""
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import BackgroundTasks, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import (
    CappeBookingSuggestionAccessRedeem,
    CappeBookingSuggestionAccessRequest,
    CappeBookingSuggestionAccessStatus,
)
from ...services.booking_suggestion_access import (
    SUGGESTION_SESSION_COOKIE,
    SUGGESTION_SESSION_TTL,
    canonical_suggestion_host,
    canonical_suggestion_origin,
    issue_suggestion_link,
    redeem_suggestion_link,
    resolve_suggestion_session,
)
from ...services.commerce import check_recipient_send_ok as _recipient_send_ok
from ...services.common import normalize_host_header
from ...services.email import (
    send_cappe_booking_suggestion_access_email,
    suggestion_access_url,
)
from ._common import _published_site, _read_rate_limit
from ._body_limit import limited_public_router

router = limited_public_router()


def _request_host(request: Request) -> str | None:
    """Read only the direct Host authority; forwarded host is untrusted."""
    return normalize_host_header(request.headers.get("host"))


def _site_host_matches(
    site: Mapping[str, Any],
    host: str | None,
    *,
    canonical_only: bool,
) -> bool:
    if not host:
        return False
    canonical = canonical_suggestion_host(site)
    if host == canonical:
        return True
    subdomain = str(site.get("subdomain") or "").lower().rstrip(".")
    if host in {f"{subdomain}.localhost", f"{subdomain}.cappe.localhost"}:
        return True
    if canonical_only:
        return False
    custom = normalize_host_header(site.get("custom_domain"))
    return bool(custom and host in {custom, f"www.{custom}"})


def _require_site_host(request: Request, site: Mapping[str, Any], *, canonical_only: bool) -> None:
    if not _site_host_matches(site, _request_host(request), canonical_only=canonical_only):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Booking access is unavailable on this host.",
        )


async def require_booking_suggestion_session(slug: str, request: Request) -> str:
    """Resolve the site-scoped HttpOnly session or reject before Gemini work."""
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        _require_site_host(request, site, canonical_only=True)
        email = await resolve_suggestion_session(
            conn,
            site_id=site["id"],
            token=request.cookies.get(SUGGESTION_SESSION_COOKIE),
            now=datetime.now(timezone.utc),
        )
    if not email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email to use AI suggestions.",
        )
    return email


@router.post(
    "/public/sites/{slug}/booking-suggestions/access",
    response_model=CappeBookingSuggestionAccessStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_booking_suggestion_access(
    slug: str,
    body: CappeBookingSuggestionAccessRequest,
    request: Request,
    background: BackgroundTasks,
):
    if body.website.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request")
    email = str(body.email).strip().lower()
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_booking_suggest_access_min", 2, 60)
    await check_rate_limit(ip, "cappe_booking_suggest_access_hr", 6, 3600)
    await check_rate_limit(email, "cappe_booking_suggest_access_email_hr", 3, 3600)

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        _require_site_host(request, site, canonical_only=False)
        async with conn.transaction():
            issued = await issue_suggestion_link(
                conn,
                site_id=site["id"],
                email=email,
                now=datetime.now(timezone.utc),
            )
        origin = canonical_suggestion_origin(site)

    if issued and origin and await _recipient_send_ok(email):
        token, client_name = issued
        background.add_task(
            send_cappe_booking_suggestion_access_email,
            email,
            client_name,
            site["name"],
            suggestion_access_url(origin, token),
        )
    # Do not reveal whether an email is a known client.
    return JSONResponse(
        content={"status": "sent"},
        status_code=status.HTTP_202_ACCEPTED,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/public/sites/{slug}/booking-suggestions/access/redeem")
async def redeem_site_booking_suggestion_access(
    slug: str,
    body: CappeBookingSuggestionAccessRedeem,
    request: Request,
    response: Response,
):
    """Redeem a one-time link on the canonical tenant host."""
    await check_rate_limit(client_ip(request), "cappe_booking_suggest_redeem", 10, 60)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        _require_site_host(request, site, canonical_only=True)
        async with conn.transaction():
            redeemed = await redeem_suggestion_link(
                conn,
                token=body.token,
                site_id=site["id"],
                now=datetime.now(timezone.utc),
            )
        if redeemed is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link")
    response.set_cookie(
        SUGGESTION_SESSION_COOKIE,
        redeemed[2],
        max_age=int(SUGGESTION_SESSION_TTL.total_seconds()),
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok"}


@router.get(
    "/public/sites/{slug}/booking-suggestions/access/status",
    response_model=CappeBookingSuggestionAccessStatus,
)
async def booking_suggestion_access_status(slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        _require_site_host(request, site, canonical_only=False)
        if not _site_host_matches(site, _request_host(request), canonical_only=True):
            return JSONResponse(
                content={"status": "required"},
                headers={"Cache-Control": "no-store"},
            )
        email = await resolve_suggestion_session(
            conn,
            site_id=site["id"],
            token=request.cookies.get(SUGGESTION_SESSION_COOKIE),
            now=datetime.now(timezone.utc),
        )
    return JSONResponse(
        content={"status": "eligible" if email else "required"},
        headers={"Cache-Control": "no-store"},
    )


__all__ = ["require_booking_suggestion_session", "router"]
