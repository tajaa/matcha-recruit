"""Tell-Us consumer "My Reviews" — the reviewer's own view of every report
they've posted as a public review (private feedback doesn't show up here;
it's brand-facing only). Reviewer keeps full control: edit anytime, withdraw
anytime, brand can never touch either.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...database import get_connection
from ..dependencies import require_consumer
from ..models.tellus import TellusAccount, TellusMyReview, TellusMyReviewUpdate, TellusReportMedia
from ._shared import _answer_rows_to_models, _media_url, effective_review_state

router = APIRouter()


async def _serialize_my_review(conn, row, viewer_id: UUID) -> TellusMyReview:
    mrows = await conn.fetch(
        "SELECT id, media_type, mime_type, original_filename, storage_path "
        "FROM tellus_report_media WHERE report_id = $1 ORDER BY created_at",
        row["id"],
    )
    media = [
        TellusReportMedia(
            id=m["id"], media_type=m["media_type"], mime_type=m["mime_type"],
            original_filename=m["original_filename"], url=_media_url(m["storage_path"]),
        )
        for m in mrows
    ]
    dm_thread_id = await conn.fetchval(
        "SELECT id FROM tellus_dm_threads WHERE report_id = $1", row["id"]
    )
    arows = await conn.fetch(
        "SELECT id, prompt_text, answer, position FROM tellus_report_answers WHERE report_id = $1 ORDER BY position",
        row["id"],
    )
    likes = await conn.fetchrow(
        "SELECT COUNT(*)::int AS like_count, COUNT(*) FILTER (WHERE account_id = $2) > 0 AS liked_by_me "
        "FROM tellus_likes WHERE report_id = $1",
        row["id"], viewer_id,
    )
    return TellusMyReview(
        id=row["id"],
        brand_name=row["brand_name"],
        brand_slug=row["brand_slug"],
        store_name=row["store_name"],
        rating=row["rating"],
        title=row["title"],
        description=row["description"],
        review_state=effective_review_state(row),
        publish_at=row["publish_at"],
        created_at=row["created_at"],
        points_awarded=row["points_awarded"] or 0,
        hearted=row["hearted_at"] is not None,
        brand_public_reply=row["brand_public_reply"],
        brand_public_reply_at=row["brand_public_reply_at"],
        dm_thread_id=dm_thread_id,
        media=media,
        answers=_answer_rows_to_models(arows),
        like_count=likes["like_count"],
        liked_by_me=likes["liked_by_me"],
    )


async def _serialize_my_reviews(conn, rows, viewer_id: UUID) -> list[TellusMyReview]:
    """Batched sibling of _serialize_my_review for the list endpoint — one
    media query and one DM-thread query for the whole page instead of 2N."""
    if not rows:
        return []

    report_ids = [r["id"] for r in rows]

    mrows = await conn.fetch(
        "SELECT id, report_id, media_type, mime_type, original_filename, storage_path "
        "FROM tellus_report_media WHERE report_id = ANY($1::uuid[]) ORDER BY created_at",
        report_ids,
    )
    media_by_report: dict = {}
    for m in mrows:
        media_by_report.setdefault(m["report_id"], []).append(
            TellusReportMedia(
                id=m["id"], media_type=m["media_type"], mime_type=m["mime_type"],
                original_filename=m["original_filename"], url=_media_url(m["storage_path"]),
            )
        )

    dm_rows = await conn.fetch(
        "SELECT id, report_id FROM tellus_dm_threads WHERE report_id = ANY($1::uuid[])", report_ids
    )
    dm_thread_by_report = {d["report_id"]: d["id"] for d in dm_rows}

    arows = await conn.fetch(
        "SELECT id, report_id, prompt_text, answer, position FROM tellus_report_answers "
        "WHERE report_id = ANY($1::uuid[]) ORDER BY report_id, position", report_ids,
    )
    answers_by_report: dict = {}
    for a in arows:
        answers_by_report.setdefault(a["report_id"], []).append(a)

    like_rows = await conn.fetch(
        "SELECT report_id, COUNT(*)::int AS like_count, "
        "  COUNT(*) FILTER (WHERE account_id = $2) > 0 AS liked_by_me "
        "FROM tellus_likes WHERE report_id = ANY($1::uuid[]) GROUP BY report_id",
        report_ids, viewer_id,
    )
    likes_by_report = {r["report_id"]: r for r in like_rows}

    return [
        TellusMyReview(
            id=r["id"],
            brand_name=r["brand_name"],
            brand_slug=r["brand_slug"],
            store_name=r["store_name"],
            rating=r["rating"],
            title=r["title"],
            description=r["description"],
            review_state=effective_review_state(r),
            publish_at=r["publish_at"],
            created_at=r["created_at"],
            points_awarded=r["points_awarded"] or 0,
            hearted=r["hearted_at"] is not None,
            brand_public_reply=r["brand_public_reply"],
            brand_public_reply_at=r["brand_public_reply_at"],
            dm_thread_id=dm_thread_by_report.get(r["id"]),
            media=media_by_report.get(r["id"], []),
            answers=_answer_rows_to_models(answers_by_report.get(r["id"], [])),
            like_count=likes_by_report.get(r["id"], {}).get("like_count", 0),
            liked_by_me=likes_by_report.get(r["id"], {}).get("liked_by_me", False),
        )
        for r in rows
    ]


async def _get_owned_review(conn, report_id: UUID, account_id: UUID) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM tellus_reports WHERE id = $1 AND reporter_account_id = $2 "
        "AND review_state IS NOT NULL",
        report_id, account_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    return dict(row)


@router.get("/me/reviews", response_model=list[TellusMyReview])
async def list_my_reviews(
    account: TellusAccount = Depends(require_consumer),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT r.*, b.name AS brand_name, b.slug AS brand_slug, s.name AS store_name
               FROM tellus_reports r
               JOIN tellus_brands b ON b.id = r.brand_id
               LEFT JOIN tellus_stores s ON s.id = r.store_id
               WHERE r.reporter_account_id = $1 AND r.review_state IS NOT NULL
               ORDER BY r.created_at DESC
               LIMIT $2 OFFSET $3""",
            account.id, limit, offset,
        )
        return await _serialize_my_reviews(conn, rows, account.id)


@router.patch("/me/reviews/{report_id}", response_model=TellusMyReview)
async def update_my_review(
    report_id: UUID, body: TellusMyReviewUpdate, account: TellusAccount = Depends(require_consumer)
):
    """Partial update of title/description/rating. Never touches publish_at —
    the 48h clock is fixed and edits don't reset it."""
    async with get_connection() as conn:
        row = await _get_owned_review(conn, report_id, account.id)
        if row["review_state"] == "withdrawn":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="This review has been withdrawn.",
            )
        updated = await conn.fetchrow(
            """UPDATE tellus_reports SET
                   title = COALESCE($2, title),
                   description = COALESCE($3, description),
                   rating = COALESCE($4, rating),
                   updated_at = NOW()
               WHERE id = $1
               RETURNING *""",
            report_id, body.title, body.description, body.rating,
        )
        full = await conn.fetchrow(
            """SELECT r.*, b.name AS brand_name, b.slug AS brand_slug, s.name AS store_name
               FROM tellus_reports r
               JOIN tellus_brands b ON b.id = r.brand_id
               LEFT JOIN tellus_stores s ON s.id = r.store_id
               WHERE r.id = $1""",
            updated["id"],
        )
        return await _serialize_my_review(conn, full, account.id)


@router.post("/me/reviews/{report_id}/withdraw", response_model=TellusMyReview)
async def withdraw_my_review(report_id: UUID, account: TellusAccount = Depends(require_consumer)):
    """Idempotent — already-withdrawn just returns the current state. Works
    whether the review is still held or already published. No un-withdraw in
    v1; gifting/grants are untouched (a gift already given stays given)."""
    async with get_connection() as conn:
        await _get_owned_review(conn, report_id, account.id)
        await conn.execute(
            "UPDATE tellus_reports SET review_state = 'withdrawn', updated_at = NOW() WHERE id = $1",
            report_id,
        )
        full = await conn.fetchrow(
            """SELECT r.*, b.name AS brand_name, b.slug AS brand_slug, s.name AS store_name
               FROM tellus_reports r
               JOIN tellus_brands b ON b.id = r.brand_id
               LEFT JOIN tellus_stores s ON s.id = r.store_id
               WHERE r.id = $1""",
            report_id,
        )
        return await _serialize_my_review(conn, full, account.id)
