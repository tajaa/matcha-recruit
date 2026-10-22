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

Paid readers (cappemag05), all for a signed-in reader (a shopper session,
`render/assets/paywall.js`):

  * `GET /public/sites/{slug}/stories/{story}/paid` — the part of a paid
    story after its paywall, as HTML, for a reader with paid access; 403
    `{code: 'subscribe'}` otherwise. `no-store`: it is never in a cache, the
    page's HTML, the feed or an issue email.
  * `POST /public/sites/{slug}/magazine/checkout` — start a subscription
    (`services/magazine/billing.py`).
  * `GET /public/sites/{slug}/magazine/me` — what the reader holds here.
"""
import hashlib
import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...dependencies import require_shopper, require_shopper_session
from ...models.cappe import CappeFollowRequest, CappeMagazineCheckout
from ...services.magazine import billing as mag_billing
from ...services.magazine import reader as mag_reader
from ...services.magazine.access import has_paid_access, reader_status
from ...services.magazine.magazines import live_magazine, preview_blocks
from ...services.magazine.pages import story_blocks
from ...services.magazine.story_render import render_blocks, split_at_paywall
from ...services.magazine.studio.render import locked_pages
from ...services.magazine.studio.schema import paywall_from
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


_PRIVATE = {"Cache-Control": "no-store, private"}


@router.get("/public/sites/{slug}/stories/{story_slug}/paid")
async def paid_part(slug: str, story_slug: str, context=Depends(require_shopper_session)):
    """The rest of a paid story, for a reader who has paid access."""
    site, shopper = context
    await check_rate_limit(str(shopper["id"]), "cappe_mag_paid", 300, 3600)
    async with get_connection() as conn:
        mag = await live_magazine(conn, site) if site["status"] == "published" else None
        post = await mag_reader.live_story(conn, site["id"], slug=story_slug) if mag else None
        if not post or post.get("access") != "paid":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
        if not await has_paid_access(conn, site["id"], shopper["id"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
                "code": "subscribe", "message": "This story is for subscribers."})
        assets = await mag_reader.story_assets(conn, site["id"], post)
    _free, rest = split_at_paywall(story_blocks(post), preview_blocks=preview_blocks(mag))
    out: dict = {"html": render_blocks(rest, assets, dropcap=False)}
    start = paywall_from(post) if post.get("format") == "pages" else None
    if start:
        # A paged story's locked pages, each as its items (the page fills its
        # empty pages), beside the rest of its Text view.
        out["pages"] = locked_pages(post["content"]["doc"], assets, start)
    return JSONResponse(out, headers=_PRIVATE)


@router.post("/public/sites/{slug}/magazine/checkout", status_code=status.HTTP_201_CREATED)
async def magazine_checkout(slug: str, body: CappeMagazineCheckout, context=Depends(require_shopper)):
    site, shopper = context
    await check_rate_limit(str(shopper["id"]), "cappe_mag_checkout", 10, 3600)
    return await mag_billing.checkout(site, shopper, body)


@router.get("/public/sites/{slug}/magazine/me")
async def magazine_me(slug: str, context=Depends(require_shopper_session)):
    site, shopper = context
    async with get_connection() as conn:
        status_ = await reader_status(conn, site["id"], shopper["id"])
    return JSONResponse(content=jsonable_encoder(status_), headers=_PRIVATE)
