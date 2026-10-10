"""Cappe public surface — reviews.

A review is about the store, or about one product. One written from a paid
order's page (`order_token`) is a verified purchase: one per product per
order. Who may post at all is the owner's call (`cappe_sites.review_submissions`)
and is enforced here — turning submissions off used to only hide the form.

Every review lands `pending` until the owner approves it. A per-store cap on
pending reviews keeps a flood from burying the moderation queue; a hidden
`website` field catches form-filling bots (they are told it worked).
"""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Query, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import CappePublicReview, CappeReviewCreate
from ._common import _published_site, _read_rate_limit

from ._body_limit import limited_public_router

router = limited_public_router()

MAX_PENDING = 500

_PUBLIC_COLS = "author_name, rating, body, created_at, product_id, verified, owner_reply, owner_replied_at"


@router.get("/public/sites/{slug}/reviews", response_model=list[CappePublicReview])
async def public_reviews(slug: str, request: Request, product_id: Optional[UUID] = Query(default=None)):
    """Approved reviews for the public site (hydrates the reviews widget), or
    for one product (the product panel). Verified purchases first."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        if product_id is not None:
            rows = await conn.fetch(
                f"SELECT {_PUBLIC_COLS} FROM cappe_reviews WHERE site_id = $1 AND product_id = $2 "
                "AND status = 'approved' ORDER BY verified DESC, created_at DESC LIMIT 50",
                site["id"], product_id,
            )
        else:
            rows = await conn.fetch(
                f"SELECT {_PUBLIC_COLS} FROM cappe_reviews "
                "WHERE site_id = $1 AND status = 'approved' ORDER BY created_at DESC LIMIT 50",
                site["id"],
            )
    return [dict(r) for r in rows]


@router.get("/public/sites/{slug}/review-settings")
async def public_review_settings(slug: str, request: Request):
    """Who may post reviews here, so the widget shows a form only when one
    can be sent."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        who = await conn.fetchval("SELECT review_submissions FROM cappe_sites WHERE id = $1", site["id"])
    return {"submissions": who or "anyone"}


@router.post("/public/sites/{slug}/reviews", status_code=status.HTTP_201_CREATED)
async def public_submit_review(slug: str, body: CappeReviewCreate, request: Request):
    """A visitor (or, with `order_token`, a buyer) submits a review. It lands
    `pending` until the owner approves it."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_review", 5, 60)
    await check_rate_limit(ip, "cappe_review_hr", 20, 3600)
    if (body.website or "").strip():
        return {"ok": True}  # a bot filled the hidden field: say yes, keep nothing
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        async with conn.transaction():
            # One admission at a time per store: the pending count and the
            # insert below must see each other, or two submissions that both
            # count 499 both get in. NO KEY UPDATE serialises admissions (and
            # a concurrent change of who may post) without blocking the
            # foreign-key checks of other writes against the store.
            who = await conn.fetchval(
                "SELECT review_submissions FROM cappe_sites WHERE id = $1 FOR NO KEY UPDATE", site["id"],
            ) or "anyone"
            if who == "off":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This store isn't taking reviews right now.")
            order_id = None
            if body.order_token:
                order = await conn.fetchrow(
                    "SELECT id, status FROM cappe_orders WHERE access_token = $1 AND site_id = $2",
                    body.order_token, site["id"],
                )
                if order is None or order["status"] not in ("paid", "fulfilled"):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                        detail="Reviews open once your order is paid.")
                if body.product_id is None or not await conn.fetchval(
                    "SELECT 1 FROM cappe_order_items WHERE order_id = $1 AND product_id = $2",
                    order["id"], body.product_id,
                ):
                    raise HTTPException(status_code=422, detail="That isn't something in this order.")
                order_id = order["id"]
            elif who == "buyers":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail="This store takes reviews from customers' order pages.")
            elif body.product_id is not None and not await conn.fetchval(
                "SELECT 1 FROM cappe_products WHERE id = $1 AND site_id = $2 AND status = 'active'",
                body.product_id, site["id"],
            ):
                raise HTTPException(status_code=422, detail="That product isn't available.")
            pending = await conn.fetchval(
                "SELECT COUNT(*) FROM cappe_reviews WHERE site_id = $1 AND status = 'pending'", site["id"],
            )
            if pending >= MAX_PENDING:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                    detail="This store isn't taking more reviews right now. Try again later.")
            inserted = await conn.fetchval(
                """INSERT INTO cappe_reviews (site_id, author_name, rating, body, status, product_id, order_id, verified)
                   VALUES ($1, $2, $3, $4, 'pending', $5, $6, $7)
                   ON CONFLICT (order_id, product_id) WHERE order_id IS NOT NULL DO NOTHING
                   RETURNING id""",
                site["id"], body.author_name.strip(), body.rating, body.body.strip(),
                body.product_id, order_id, order_id is not None,
            )
    if inserted is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You've already reviewed this from this order.")
    return {"ok": True}
