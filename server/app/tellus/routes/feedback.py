"""Tell-Us brand-side feedback dashboard — list, triage, moderate.

Brand accounts only; every query scopes by the caller's brand_id. Media URLs are
minted (presigned) at read time in the serializer.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ...database import get_connection
from ..dependencies import require_brand
from ..models.tellus import (
    TellusAccount,
    TellusFeedbackStats,
    TellusReport,
    TellusReportModerate,
    TellusReportStatusUpdate,
)
from ._shared import get_owned_report, serialize_report

router = APIRouter()


@router.get("/feedback", response_model=list[TellusReport])
async def list_feedback(
    account: TellusAccount = Depends(require_brand),
    store_id: Optional[UUID] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    sentiment: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List feedback for the brand, newest first, with optional filters. Hides
    moderator-removed reports from the default view."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT * FROM tellus_reports
               WHERE brand_id = $1
                 AND moderation_status <> 'removed'
                 AND ($2::uuid IS NULL OR store_id = $2)
                 AND ($3::text IS NULL OR status = $3)
                 AND ($4::text IS NULL OR sentiment = $4)
               ORDER BY created_at DESC
               LIMIT $5 OFFSET $6""",
            account.brand_id, store_id, status_filter, sentiment, limit, offset,
        )
        return [await serialize_report(conn, r) for r in rows]


@router.get("/feedback/stats", response_model=TellusFeedbackStats)
async def feedback_stats(account: TellusAccount = Depends(require_brand)):
    """Sentiment + category rollup for the brand dashboard header."""
    async with get_connection() as conn:
        agg = await conn.fetchrow(
            """SELECT
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'new') AS new,
                   COUNT(*) FILTER (WHERE sentiment = 'positive') AS positive,
                   COUNT(*) FILTER (WHERE sentiment = 'neutral') AS neutral,
                   COUNT(*) FILTER (WHERE sentiment = 'negative') AS negative
               FROM tellus_reports
               WHERE brand_id = $1 AND moderation_status <> 'removed'""",
            account.brand_id,
        )
        cats = await conn.fetch(
            "SELECT category, COUNT(*) AS n FROM tellus_reports "
            "WHERE brand_id = $1 AND moderation_status <> 'removed' GROUP BY category",
            account.brand_id,
        )
    return TellusFeedbackStats(
        total=agg["total"], new=agg["new"], positive=agg["positive"],
        neutral=agg["neutral"], negative=agg["negative"],
        by_category={c["category"]: c["n"] for c in cats},
    )


@router.get("/feedback/{report_id}", response_model=TellusReport)
async def get_feedback(report_id: UUID, account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        row = await get_owned_report(conn, report_id, account.brand_id)
        return await serialize_report(conn, row)


@router.patch("/feedback/{report_id}/status", response_model=TellusReport)
async def update_status(
    report_id: UUID, body: TellusReportStatusUpdate, account: TellusAccount = Depends(require_brand)
):
    async with get_connection() as conn:
        await get_owned_report(conn, report_id, account.brand_id)
        row = await conn.fetchrow(
            "UPDATE tellus_reports SET status = $3, updated_at = NOW() "
            "WHERE id = $1 AND brand_id = $2 RETURNING *",
            report_id, account.brand_id, body.status,
        )
        return await serialize_report(conn, row)


@router.patch("/feedback/{report_id}/moderation", response_model=TellusReport)
async def moderate(
    report_id: UUID, body: TellusReportModerate, account: TellusAccount = Depends(require_brand)
):
    """Brand flags/removes abusive UGC (review finding G). A removed report is
    hidden from the default list; the media stays in S3 for takedown audit."""
    async with get_connection() as conn:
        await get_owned_report(conn, report_id, account.brand_id)
        row = await conn.fetchrow(
            "UPDATE tellus_reports SET moderation_status = $3, updated_at = NOW() "
            "WHERE id = $1 AND brand_id = $2 RETURNING *",
            report_id, account.brand_id, body.moderation_status,
        )
        return await serialize_report(conn, row)
