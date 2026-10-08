"""Shopper sign-in for the web storefront — the refresh token in a cookie.

The iOS app keeps its refresh token in the Keychain and sends it in a body
(`/shopper/auth/*`). A web page has nowhere that safe for it, so here the
refresh token lives in a host-only, HttpOnly, Secure, SameSite=Strict
`__Host-` cookie on the store's own host (the storefront calls `/api/cappe`
on its own origin), and only the short-lived access token reaches the page,
held in memory. The emailed-code endpoints (`/shopper/auth/start`) are shared.

Cookie-authenticated endpoints also require an `X-Cappe-Web: 1` header: a
cross-site form can't send one, and a cross-site script can't without a CORS
preflight this API never grants.

Signing out on the web ends THIS session only. The app's `/auth/logout`
revokes every session and device — which would sign a shopper out of the app
on their phone for signing out of a laptop.

A store that has closed to shoppers (unpublished, owner inactive, a plan
without shopper accounts) still lets the people it bills sign in and refresh,
to cancel; `store_open` tells the page to offer only that.
"""
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.database import get_connection
from app.cappe.dependencies import require_shopper
from app.cappe.models.shopper import ShopperVerify
from app.cappe.services import shopper_auth as auth
from app.cappe.services.common import site_origins, url_within_origins
from app.cappe.services.stripe_connect import CappeStripeError, get_cappe_stripe
from ._body_limit import limited_public_router

router = limited_public_router(16384)
PREFIX = "/public/sites/{slug}/shopper"
COOKIE = "__Host-cz_shopper"


def _cookie_max_age() -> int:
    """As long as the refresh token itself can live (its absolute limit)."""
    try:
        days = int(get_settings().cappe_shopper_refresh_absolute_days)
    except Exception:  # noqa: BLE001 — settings not loaded (tests); the default
        days = 180
    return days * 86400


def _set_refresh(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE, token, max_age=_cookie_max_age(), path="/", secure=True, httponly=True, samesite="strict",
    )


def _clear_refresh(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")


def _web_only(request: Request) -> None:
    if request.headers.get("x-cappe-web") != "1":
        raise HTTPException(403, "Missing web client header")


def _for_page(session: dict, store_open: bool) -> dict:
    """The session minus the refresh token, which stays in the cookie."""
    return {**{k: v for k, v in session.items() if k != "refresh_token"}, "store_open": store_open}


@router.post(PREFIX + "/web/verify")
async def web_verify(slug: str, body: ShopperVerify, request: Request, response: Response):
    """Exchange an emailed code for a session: refresh token in the cookie,
    access token in the body."""
    _web_only(request)
    await check_rate_limit(client_ip(request), "cappe_shopper_verify", 30, 900)
    async with get_connection() as conn:
        site, store_open = await auth.sign_in_site(conn, slug)
        session = None
        if store_open or await auth.subscribes_here(conn, site["id"], str(body.email)):
            session = await auth.verify_login_code(conn, site=site, email=str(body.email), code=body.code)
    if session is None:
        raise HTTPException(401, "That code is wrong or has expired")
    _set_refresh(response, session["refresh_token"])
    return _for_page(session, store_open)


@router.post(PREFIX + "/web/refresh")
async def web_refresh(slug: str, request: Request, response: Response):
    """A fresh access token from the cookie, rotating the refresh token.
    401 (and the cookie cleared) when there is no live session.

    A cookie the session has already rotated past is 401 WITHOUT clearing: it
    comes from a second request racing the one that rotated it, whose
    response set the newer cookie this browser now holds — clearing would
    delete that one. `stale: true` tells the page to retry with it."""
    _web_only(request)
    await check_rate_limit(client_ip(request), "cappe_shopper_refresh", 120, 3600)
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not signed in")
    try:
        async with get_connection() as conn:
            site, store_open = await auth.session_site(conn, slug)
            async with conn.transaction():
                shopper, payload = await auth.resolve_shopper(conn, site, token, "refresh", lock=True)
                session = await auth.issue_session(
                    conn, shopper, sid=UUID(payload["sid"]), started=payload["session_started_at"],
                )
    except auth.StaleRefresh as exc:
        response.status_code = 401
        return {"detail": exc.detail, "stale": True}
    except HTTPException as exc:
        if exc.status_code == 401:
            _clear_refresh(response)
            # The cookie must be cleared on THIS response, so it is returned,
            # not raised (a raised HTTPException drops the Set-Cookie).
            response.status_code = 401
            return {"detail": exc.detail}
        raise
    _set_refresh(response, session["refresh_token"])
    return _for_page(session, store_open)


@router.post(PREFIX + "/web/logout", status_code=204)
async def web_logout(slug: str, request: Request):
    """End this browser's session — and only this one.

    Takes the shopper lock refresh takes (`resolve_shopper(lock=True)`): a
    refresh already under way finishes first and its rotated session is the
    one deleted; one that starts after finds no session. Without it a refresh
    could re-create the session a successful sign-out had just deleted. A
    failure here is a 500 with the cookie left in place — the session is
    still live, so the page reports it and offers a retry."""
    _web_only(request)
    token = request.cookies.get(COOKIE)
    out = Response(status_code=204)
    _clear_refresh(out)
    if not token:
        return out
    payload = auth.token_helpers().decode_token(token, "refresh")
    try:
        sid, shopper_id = UUID(payload["sid"]), UUID(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return out
    async with get_connection() as conn, conn.transaction():
        await conn.execute("SELECT 1 FROM cappe_shoppers WHERE id = $1 FOR UPDATE", shopper_id)
        await conn.execute(
            "DELETE FROM cappe_shopper_sessions WHERE id = $1 AND shopper_id = $2", sid, shopper_id,
        )
    return out


class PortalRequest(BaseModel):
    return_url: str = Field(min_length=1, max_length=2000)


@router.post(PREFIX + "/me/billing-portal")
async def billing_portal(body: PortalRequest, request: Request, context=Depends(require_shopper)):
    """Stripe's page for updating the card a shopper's subscriptions charge,
    on the store's own Stripe account."""
    site, shopper = context
    await check_rate_limit(str(shopper["id"]), "cappe_shopper_portal", 20, 3600)
    return_url = url_within_origins(body.return_url, site_origins(site))
    if not return_url:
        raise HTTPException(422, "Return to this store's own pages")
    if not shopper.get("stripe_customer_id"):
        raise HTTPException(409, "There's no card on file for you at this store yet.")
    async with get_connection() as conn:
        owner = await conn.fetchrow(
            "SELECT id, stripe_account_id, stripe_portal_config_id FROM cappe_accounts WHERE id = $1",
            site["account_id"],
        )
    if not owner or not owner["stripe_account_id"]:
        raise HTTPException(409, "This store isn't taking card payments right now.")
    stripe = get_cappe_stripe()
    try:
        config_id = owner["stripe_portal_config_id"]
        if not config_id:
            config_id = await stripe.create_portal_configuration(owner["stripe_account_id"])
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE cappe_accounts SET stripe_portal_config_id = COALESCE(stripe_portal_config_id, $2) "
                    "WHERE id = $1",
                    owner["id"], config_id,
                )
        session = await stripe.create_connected_portal_session(
            account_id=owner["stripe_account_id"], customer_id=shopper["stripe_customer_id"],
            return_url=return_url, configuration_id=config_id,
        )
    except CappeStripeError:
        raise HTTPException(502, "Couldn't reach Stripe. Try again in a moment.")
    return {"url": session["url"]}
