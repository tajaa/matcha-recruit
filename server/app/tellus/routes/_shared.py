"""Shared helpers for Tell-Us routes — ownership checks + media URL minting."""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status

from ...core.services.storage import get_storage
from ..models.tellus import TellusReport, TellusReportMedia


async def get_owned_store(conn, store_id: UUID, brand_id: UUID) -> dict:
    """Fetch a store, 404 if it isn't owned by this brand."""
    row = await conn.fetchrow(
        "SELECT * FROM tellus_stores WHERE id = $1 AND brand_id = $2", store_id, brand_id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return dict(row)


async def get_owned_report(conn, report_id: UUID, brand_id: UUID) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM tellus_reports WHERE id = $1 AND brand_id = $2", report_id, brand_id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return dict(row)


def _media_url(storage_path: Optional[str]) -> Optional[str]:
    """Presigned download/playback URL for a private media object (15 min)."""
    if not storage_path:
        return None
    return get_storage().get_presigned_download_url(storage_path, expires_in=900)


async def serialize_report(conn, row, *, include_media: bool = True) -> TellusReport:
    """Row → TellusReport, minting presigned media URLs at read time."""
    store_name = None
    if row["store_id"] is not None:
        store_name = await conn.fetchval("SELECT name FROM tellus_stores WHERE id = $1", row["store_id"])

    media: list[TellusReportMedia] = []
    if include_media:
        mrows = await conn.fetch(
            "SELECT id, media_type, mime_type, original_filename, storage_path "
            "FROM tellus_report_media WHERE report_id = $1 ORDER BY created_at",
            row["id"],
        )
        media = [
            TellusReportMedia(
                id=m["id"],
                media_type=m["media_type"],
                mime_type=m["mime_type"],
                original_filename=m["original_filename"],
                url=_media_url(m["storage_path"]),
            )
            for m in mrows
        ]

    return TellusReport(
        id=row["id"],
        brand_id=row["brand_id"],
        store_id=row["store_id"],
        store_name=store_name,
        report_number=row["report_number"],
        category=row["category"],
        sentiment=row["sentiment"],
        title=row["title"],
        description=row["description"],
        occurred_at=row["occurred_at"],
        reporter_contact=row["reporter_contact"],
        usefulness_score=row["usefulness_score"],
        status=row["status"],
        ai_summary=row["ai_summary"],
        ai_category=row["ai_category"],
        ai_sentiment=row["ai_sentiment"],
        moderation_status=row["moderation_status"],
        created_at=row["created_at"],
        media=media,
    )
