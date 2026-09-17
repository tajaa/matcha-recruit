"""Cappe public surface — newsletter subscribe/confirm/unsubscribe."""
from html import escape
from uuid import UUID

from fastapi import HTTPException, Request, status
from fastapi.responses import HTMLResponse

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import CappeSubscribeRequest
from ._body_limit import limited_public_router
from ._common import _published_site, _read_rate_limit, _reject_reserved


router = limited_public_router()


@router.post("/public/sites/{slug}/subscribe", status_code=status.HTTP_201_CREATED)
async def public_subscribe(slug: str, body: CappeSubscribeRequest, request: Request):
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_subscribe", 5, 60)
    await check_rate_limit(ip, "cappe_subscribe_hr", 20, 3600)
    # TODO(captcha): verify an hCaptcha/Turnstile token before insert (list-bombing surface).
    email = str(body.email).strip().lower()
    _reject_reserved(email)

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        # Re-subscribe resurrects a previously-unsubscribed/bounced row.
        await conn.execute(
            """INSERT INTO cappe_subscribers (site_id, email, name, source, status)
               VALUES ($1, $2, $3, 'website', 'subscribed')
               ON CONFLICT (site_id, email)
               DO UPDATE SET status = 'subscribed', unsubscribed_at = NULL,
                             name = COALESCE(EXCLUDED.name, cappe_subscribers.name),
                             updated_at = NOW()""",
            site["id"], email, body.name,
        )
    return {"ok": True}


@router.get("/public/sites/{slug}/unsubscribe/{token}")
async def public_unsubscribe(slug: str, token: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        await conn.execute(
            "UPDATE cappe_subscribers SET status = 'unsubscribed', unsubscribed_at = NOW(), updated_at = NOW() "
            "WHERE site_id = $1 AND unsubscribe_token = $2 AND status != 'unsubscribed'",
            site["id"], token,
        )
    # Idempotent: a bad/used token still returns ok. Return a constant shape so
    # the response can't be used to distinguish a valid unsubscribe token from an
    # invalid one (the old `updated` flag leaked exactly that).
    return {"ok": True}


def _confirm_page(heading: str, message: str, status_code: int = 200) -> HTMLResponse:
    """Minimal standalone page for a link clicked out of an email client.

    Deliberately self-contained (no site theme, no JS): the person may not have
    a site open, and this must render identically from any mail client.
    """
    return HTMLResponse(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{escape(heading)}</title></head>"
        "<body style=\"margin:0;min-height:100vh;display:grid;place-items:center;"
        "background:#0b0b0d;color:#e4e4e7;font:16px system-ui,sans-serif\">"
        f"<main style=\"max-width:32rem;padding:2rem;text-align:center\"><h1>{escape(heading)}</h1>"
        f"<p style=\"color:#a1a1aa;line-height:1.6\">{escape(message)}</p></main></body></html>",
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/public/subscribe/confirm/{token}", response_class=HTMLResponse)
async def public_confirm_subscription(token: str, request: Request):
    """Double opt-in landing for a subscriber a business imported.

    Imported contacts are staged `pending_confirmation` (routes/clients.py); the
    campaign worker only ever selects `subscribed`, so this click is what makes
    an imported address mailable. Idempotent — a second click on the same link
    is a success, not an error — and unknown tokens 404 without saying anything
    about which addresses exist.
    """
    await _read_rate_limit(request)
    try:
        confirm_token = UUID(token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown confirmation link")

    async with get_connection() as conn:
        confirmed = await conn.fetchval(
            """UPDATE cappe_subscribers
                  SET status = 'subscribed', unsubscribed_at = NULL, updated_at = NOW()
                WHERE confirm_token = $1 AND status = 'pending_confirmation'
             RETURNING id""",
            confirm_token,
        )
        if confirmed is None:
            # Token kept on the row after confirmation on purpose, so a re-click
            # (mail clients prefetch links) reads as done rather than expired.
            known = await conn.fetchval(
                "SELECT 1 FROM cappe_subscribers WHERE confirm_token = $1", confirm_token
            )
            if not known:
                return _confirm_page(
                    "Link not found",
                    "This confirmation link is no longer valid.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
    return _confirm_page(
        "You're subscribed",
        "Thanks — you'll start receiving emails from this business. "
        "Every one of them carries an unsubscribe link.",
    )
