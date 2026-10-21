"""Cappe public surface — following a magazine, and leaving its email.

`POST /public/sites/{slug}/follow`: a reader asks for new stories by email.
It is double opt-in, unlike the plain site subscribe: the row is staged
`pending_confirmation` with `source='follow'` and `workers/tasks/
cappe_subscribe_confirm.py` mails the confirmation. It never touches an
address already subscribed (or bounced), and never makes one mailable
without the confirmation. The answer is always the same 202, so it can't be
used to learn who follows a magazine; one address gets at most three
confirmation emails a day per magazine.

`POST /public/sites/{slug}/unsubscribe/{token}/one-click`: the RFC 8058
List-Unsubscribe-Post target an issue email carries, so a mail client's
"Unsubscribe" button works without opening a page. It works whatever the
site's status: leaving must never depend on the magazine still being up.
"""
import hashlib
import logging

from fastapi import HTTPException, Request, status
from fastapi.responses import Response

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import CappeFollowRequest
from ...services.magazine.magazines import live_magazine
from ._body_limit import limited_public_router
from ._common import _read_rate_limit, _reject_reserved

logger = logging.getLogger(__name__)

router = limited_public_router()

CONFIRMATIONS_PER_DAY = 3
_ACCEPTED = {"ok": True, "message": "Check your inbox to confirm."}


def _dispatch_confirm(site_id) -> None:
    try:
        from app.workers.tasks.cappe_subscribe_confirm import run_cappe_subscribe_confirm

        run_cappe_subscribe_confirm.delay(str(site_id))
    except Exception as exc:  # noqa: BLE001 — the row waits for the next dispatch
        logger.warning("follow confirmation dispatch failed for %s: %s", site_id, type(exc).__name__)


@router.post("/public/sites/{slug}/follow", status_code=status.HTTP_202_ACCEPTED)
async def follow_magazine(slug: str, body: CappeFollowRequest, request: Request):
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_subscribe", 5, 60)
    await check_rate_limit(ip, "cappe_subscribe_hr", 20, 3600)
    email = str(body.email).strip().lower()
    _reject_reserved(email)
    async with get_connection() as conn:
        site = await conn.fetchrow("SELECT id, account_id, status FROM cappe_sites WHERE slug = $1", slug)
        mag = await live_magazine(conn, site) if site and site["status"] == "published" else None
    if not mag or not mag.get("follow_enabled", True):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Magazine not found")
    digest = hashlib.sha256(f"{site['id']}:{email}".encode()).hexdigest()[:32]
    try:
        await check_rate_limit(digest, "cappe_follow_email", CONFIRMATIONS_PER_DAY, 86_400)
    except HTTPException:
        return _ACCEPTED  # the same answer; no more email to that address today
    async with get_connection() as conn:
        staged = await conn.fetchval(
            """INSERT INTO cappe_subscribers (site_id, email, name, source, status, confirm_token)
               VALUES ($1, $2, $3, 'follow', 'pending_confirmation', gen_random_uuid())
               ON CONFLICT (site_id, email) DO UPDATE
                  SET status = 'pending_confirmation', source = 'follow',
                      confirm_token = COALESCE(cappe_subscribers.confirm_token, gen_random_uuid()),
                      confirm_sent_at = NULL,
                      name = COALESCE(EXCLUDED.name, cappe_subscribers.name), updated_at = NOW()
                WHERE cappe_subscribers.status IN ('unsubscribed', 'pending_confirmation', 'pending')
               RETURNING id""",
            site["id"], email, (body.name or "").strip() or None,
        )
    if staged:
        _dispatch_confirm(site["id"])
    return _ACCEPTED


@router.post("/public/sites/{slug}/unsubscribe/{token}/one-click")
async def one_click_unsubscribe(slug: str, token: str, request: Request):
    await _read_rate_limit(request)
    if len(token) > 64:
        return Response(status_code=status.HTTP_200_OK)
    async with get_connection() as conn:
        await conn.execute(
            """UPDATE cappe_subscribers SET status = 'unsubscribed', unsubscribed_at = NOW(), updated_at = NOW()
                WHERE unsubscribe_token = $1 AND status <> 'unsubscribed'
                  AND site_id = (SELECT id FROM cappe_sites WHERE slug = $2)""",
            token, slug,
        )
    # The same answer whether or not the token was known.
    return Response(status_code=status.HTTP_200_OK)
