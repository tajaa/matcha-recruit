"""Cappe reviews — creator moderation (owner side).

Public submission + the approved-reviews widget feed live in public.py. A review
lands `pending` and only renders on the site once the creator approves it.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeReview, CappeReviewModerate
from ._shared import get_owned_site

router = APIRouter()

_COLS = "id, site_id, author_name, rating, body, status, created_at"


@router.get("/sites/{site_id}/reviews", response_model=list[CappeReview])
async def list_reviews(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_COLS} FROM cappe_reviews WHERE site_id = $1 ORDER BY created_at DESC",
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
        row = await conn.fetchrow(
            f"UPDATE cappe_reviews SET status = $1 WHERE id = $2 AND site_id = $3 RETURNING {_COLS}",
            body.status, review_id, site_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    return dict(row)


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
