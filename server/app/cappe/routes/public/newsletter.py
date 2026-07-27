"""Cappe public surface — newsletter subscribe/unsubscribe."""
from fastapi import APIRouter, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import CappeSubscribeRequest
from ._common import _published_site, _read_rate_limit, _reject_reserved

router = APIRouter()


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
