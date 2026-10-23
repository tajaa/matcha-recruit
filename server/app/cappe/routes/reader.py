"""Cappe — a reader's dashboard on gummfit.com (cappemag06).

A reader account (`account_type='reader'`) subscribes to magazines and sells
nothing. Everything here is matched by the account's confirmed email to the
reader's row on each magazine (`services/magazine/shelf.py`), so it works
for any account that reads magazines, and a subscription started on a
magazine's own site appears here too.

  * `GET  /reader/magazines` — the shelf: each magazine held, its
    subscription or free months, and its latest story.
  * `GET  /reader/magazines/{slug}` — one magazine: what the reader holds,
    whether it takes subscribers, and its stories, newest first.
  * `GET  /reader/magazines/{slug}/stories/{story}` — the story page as HTML
    for the dashboard's frame, whole for a reader with paid access and cut at
    the paywall otherwise. `no-store`: it can hold the paid part.
  * `POST /reader/magazines/{slug}/subscribe` — Stripe Checkout, returning
    to the dashboard (`services/magazine/billing.checkout`); a return off
    gummfit.com becomes the magazine's dashboard page.
  * `POST /reader/subscriptions/{id}/cancel|resume` — stop at the period's
    end, or keep it.
  * `PUT|DELETE /reader/magazines/{slug}/follow` — follow a magazine from the
    account, or stop (`services/magazine/follows.py`; no email is sent).
  * `GET  /reader/following` and `GET /reader/feed` — the magazines followed,
    and their newest stories.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeMagazineCheckout
from ..services import recurring
from ..services.common import site_public_origin, url_within_origins
from ..services.email import app_origin, dashboard_url
from ..services.magazine import billing as mag_billing
from ..services.magazine import follows
from ..services.magazine import pages as mag_pages
from ..services.magazine import reader as mag_reader
from ..services.magazine import shelf
from ..services.magazine.access import has_paid_access, reader_status
from ..services.magazine.magazines import preview_blocks
from .render import _nav, _site_dict

router = APIRouter()

PAGE_SIZE = 12
_PRIVATE = {"Cache-Control": "no-store, private"}


def _private(content: Any) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(content), headers=_PRIVATE)


async def _taking_subscribers(conn, site: dict) -> bool:
    try:
        await mag_billing.paid_ready(conn, site)
    except HTTPException:
        return False
    return True


@router.get("/reader/magazines")
async def my_magazines(account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        email = await shelf.confirmed_email(conn, account.id)
        return _private({"magazines": await shelf.shelf(conn, email)})


@router.get("/reader/magazines/{slug}")
async def magazine(slug: str, page: int = Query(default=1, ge=1, le=50),
                   account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        email = await shelf.confirmed_email(conn, account.id)
        site, mag = await shelf.published_magazine(conn, slug)
        shopper = await shelf.shopper_for(conn, site["id"], email)
        held = await reader_status(conn, site["id"], shopper["id"]) if shopper else {
            "has_access": False, "subscription": None, "comp": None}
        open_ = await _taking_subscribers(conn, site)
        posts = await mag_reader.live_stories(conn, site["id"], limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE)
        found = await mag_reader.covers(conn, site["id"], posts[:PAGE_SIZE])
        following = await follows.is_following(conn, account.id, site["id"])
    return _private({
        "site_id": site["id"], "slug": slug, "name": mag.get("name") or site["name"], "tagline": mag.get("tagline"),
        "accent": mag.get("accent"), "origin": site_public_origin(site),
        "price_cents": mag.get("price_cents") if open_ else None, "currency": (site.get("currency") or "USD").upper(),
        "paid_pitch": mag.get("paid_pitch") if open_ else None, "taking_subscribers": open_, **held,
        "stories": [shelf.story_card(p, found.get(str(p["id"]))) for p in posts[:PAGE_SIZE]],
        "has_more": len(posts) > PAGE_SIZE, "page": page, "following": following,
    })


@router.get("/reader/magazines/{slug}/stories/{story_slug}")
async def read_story(slug: str, story_slug: str, view: Optional[str] = None,
                     account: CappeAccount = Depends(require_cappe_account)):
    """The story as its magazine prints it (`view=text`: a paged story's
    Text view, as `/stories/{slug}/text` on the site). Scripts don't run in
    the dashboard's frame, so the paid part is put in here rather than fetched."""
    await check_rate_limit(str(account.id), "cappe_reader_story", 300, 3600)
    async with get_connection() as conn:
        email = await shelf.confirmed_email(conn, account.id)
        site, mag = await shelf.published_magazine(conn, slug)
        post = await mag_reader.live_story(conn, site["id"], slug=story_slug)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
        paid = post.get("access") == "paid"
        shopper = await shelf.shopper_for(conn, site["id"], email) if paid else None
        access = bool(shopper) and await has_paid_access(conn, site["id"], shopper["id"])
        assets = await mag_reader.story_assets(conn, site["id"], post)
        more = await mag_reader.live_stories(conn, site["id"], exclude=post["id"], limit=3)
        more_covers = await mag_reader.covers(conn, site["id"], more)
        nav = await _nav(conn, site["id"])
    # With access the whole story is printed: the paywall marker renders as nothing.
    shown = {**post, "access": "free"} if access else post
    html = mag_pages.render_story(_site_dict(site, magazine=mag), nav, mag, shown, assets, more=more,
                                  more_covers=more_covers, origin=site_public_origin(site) or "",
                                  preview_blocks=preview_blocks(mag), currency=site.get("currency"),
                                  text_view=view == "text" and post.get("format") == "pages")
    return _private({"html": html, "paid": paid, "has_access": access or not paid, "title": post.get("title")})


@router.post("/reader/magazines/{slug}/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(slug: str, body: CappeMagazineCheckout, account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_reader_checkout", 10, 3600)
    async with get_connection() as conn:
        email = await shelf.confirmed_email(conn, account.id)
        site, _mag = await shelf.published_magazine(conn, slug)
        reader = await shelf.ensure_shopper(conn, site["id"], email)
    # Off our own origin, a return is dropped for the magazine's dashboard page
    # (as plan checkout does): Stripe would otherwise link anywhere it's told.
    home = dashboard_url(mag_pages.reader_path(slug))
    returns = CappeMagazineCheckout(
        success_url=url_within_origins(body.success_url, [app_origin()]) or f"{home}?subscribed=1",
        cancel_url=url_within_origins(body.cancel_url, [app_origin()]) or home,
    )
    return await mag_billing.checkout(site, reader, returns, return_origins=[app_origin()])


async def _change(subscription_id: UUID, account: CappeAccount, cancel: bool) -> dict:
    async with get_connection() as conn:
        email = await shelf.confirmed_email(conn, account.id)
        row = await shelf.own_subscription(conn, subscription_id, email)
        if not cancel:
            site = await conn.fetchrow("SELECT * FROM cappe_sites WHERE id = $1 AND status = 'published'",
                                       row["site_id"])
            if not site or not await _taking_subscribers(conn, dict(site)):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="This magazine isn't taking subscriptions now.")
    return await recurring.change_subscription(row, cancel)


@router.post("/reader/subscriptions/{subscription_id}/cancel")
async def cancel(subscription_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Stop at the end of the month already paid for."""
    await check_rate_limit(str(account.id), "cappe_reader_sub_change", 30, 3600)
    return await _change(subscription_id, account, True)


@router.post("/reader/subscriptions/{subscription_id}/resume")
async def resume(subscription_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Keep a subscription that was set to stop."""
    await check_rate_limit(str(account.id), "cappe_reader_sub_change", 30, 3600)
    return await _change(subscription_id, account, False)


@router.get("/reader/following")
async def following(account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        return _private({"magazines": await follows.following(conn, account.id)})


@router.get("/reader/feed")
async def feed(page: int = Query(default=1, ge=1, le=follows.FEED_MAX_PAGE),
               account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        return _private(await follows.feed(conn, account.id, page=page))


@router.put("/reader/magazines/{slug}/follow")
async def follow(slug: str, account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_reader_follow", 120, 3600)
    async with get_connection() as conn:
        site, _mag = await shelf.published_magazine(conn, slug)
        await follows.follow(conn, account.id, site)
    return _private({"following": True})


@router.delete("/reader/magazines/{slug}/follow")
async def unfollow(slug: str, account: CappeAccount = Depends(require_cappe_account)):
    """Works on a magazine that is down too, so it can leave the list."""
    await check_rate_limit(str(account.id), "cappe_reader_follow", 120, 3600)
    async with get_connection() as conn:
        site_id = await conn.fetchval("SELECT id FROM cappe_sites WHERE slug = $1", slug)
        if site_id:
            await follows.unfollow(conn, account.id, site_id)
    return _private({"following": False})
