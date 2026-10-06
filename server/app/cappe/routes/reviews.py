"""Cappe reviews — creator moderation (owner side).

Public submission + the approved-reviews widget feed live in public/reviews.py.
A review lands `pending` and only renders on the site once the creator
approves it. The owner can answer one publicly, and decides who may post at
all (`review_submissions`: anyone / buyers / off).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount, CappeReview, CappeReviewModerate, CappeReviewReply, CappeReviewSettings,
)
from ._shared import get_owned_site

router = APIRouter()

_COLS = ("r.id, r.site_id, r.author_name, r.rating, r.body, r.status, r.created_at, r.product_id, "
         "p.name AS product_name, r.verified, r.owner_reply, r.owner_replied_at")
_FROM = "cappe_reviews r LEFT JOIN cappe_products p ON p.id = r.product_id"


async def _review(conn, site_id: UUID, review_id: UUID):
    row = await conn.fetchrow(f"SELECT {_COLS} FROM {_FROM} WHERE r.id = $1 AND r.site_id = $2", review_id, site_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    return dict(row)


@router.get("/sites/{site_id}/reviews", response_model=list[CappeReview])
async def list_reviews(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_COLS} FROM {_FROM} WHERE r.site_id = $1 ORDER BY r.created_at DESC LIMIT 1000",
            site_id,
        )
    return [dict(r) for r in rows]


@router.patch("/sites/{site_id}/reviews/{review_id}", response_model=CappeReview)
async def moderate_review(
    site_id: UUID, review_id: UUID, body: CappeReviewModerate,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Approve / hide / un-decide a review."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        updated = await conn.fetchval(
            "UPDATE cappe_reviews SET status = $1 WHERE id = $2 AND site_id = $3 RETURNING id",
            body.status, review_id, site_id,
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
        return await _review(conn, site_id, review_id)


@router.put("/sites/{site_id}/reviews/{review_id}/reply", response_model=CappeReview)
async def reply_to_review(
    site_id: UUID, review_id: UUID, body: CappeReviewReply,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Answer a review publicly (shown under it once it's approved); an empty
    reply removes the answer."""
    reply = (body.reply or "").strip() or None
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        updated = await conn.fetchval(
            "UPDATE cappe_reviews SET owner_reply = $1, "
            "owner_replied_at = CASE WHEN $1::text IS NULL THEN NULL ELSE NOW() END "
            "WHERE id = $2 AND site_id = $3 RETURNING id",
            reply, review_id, site_id,
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
        return await _review(conn, site_id, review_id)


@router.get("/sites/{site_id}/review-settings", response_model=CappeReviewSettings)
async def get_review_settings(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
    return {"submissions": site.get("review_submissions") or "anyone"}


@router.put("/sites/{site_id}/review-settings", response_model=CappeReviewSettings)
async def set_review_settings(
    site_id: UUID, body: CappeReviewSettings, account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await conn.execute(
            "UPDATE cappe_sites SET review_submissions = $1, updated_at = NOW() WHERE id = $2",
            body.submissions, site_id,
        )
    return {"submissions": body.submissions}


@router.delete("/sites/{site_id}/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    site_id: UUID, review_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_reviews WHERE id = $1 AND site_id = $2", review_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
