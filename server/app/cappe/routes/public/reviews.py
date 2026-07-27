"""Cappe public surface — reviews."""
from fastapi import APIRouter, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import CappePublicReview, CappeReviewCreate
from ._common import _published_site, _read_rate_limit

router = APIRouter()


@router.get("/public/sites/{slug}/reviews", response_model=list[CappePublicReview])
async def public_reviews(slug: str, request: Request):
    """Approved reviews for the public site (hydrates the reviews widget)."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            "SELECT author_name, rating, body, created_at FROM cappe_reviews "
            "WHERE site_id = $1 AND status = 'approved' ORDER BY created_at DESC LIMIT 50",
            site["id"],
        )
    return [dict(r) for r in rows]


@router.post("/public/sites/{slug}/reviews", status_code=status.HTTP_201_CREATED)
async def public_submit_review(slug: str, body: CappeReviewCreate, request: Request):
    """Visitor submits a review (lands `pending` until the creator approves)."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_review", 5, 60)
    await check_rate_limit(ip, "cappe_review_hr", 20, 3600)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        await conn.execute(
            "INSERT INTO cappe_reviews (site_id, author_name, rating, body, status) "
            "VALUES ($1, $2, $3, $4, 'pending')",
            site["id"], body.author_name.strip(), body.rating, body.body.strip(),
        )
    return {"ok": True}
