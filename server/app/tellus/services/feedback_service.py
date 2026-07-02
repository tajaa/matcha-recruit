"""Tell-Us feedback intake + usefulness → points.

Creates a report (+ its media rows), scores how *useful* the feedback is, and —
when a logged-in consumer submitted it — awards points through
`points_service.award_points`. Anonymous feedback still lands; it just earns 0.
"""
import logging
import secrets
from typing import Optional
from uuid import UUID

from .points_service import award_points

logger = logging.getLogger(__name__)

# Below this usefulness score, feedback lands but earns no base points.
USEFULNESS_THRESHOLD = 20


def score_usefulness(description: str, has_media: bool, has_title: bool,
                     has_occurred_at: bool, identified: bool) -> int:
    """Heuristic 0-100 usefulness. Longer, media-backed, attributable feedback
    scores higher. (A Gemini signal can refine this later — see plan §4.)"""
    score = 10
    score += min(len((description or "").strip()) // 20, 30)  # up to +30 for detail
    if has_media:
        score += 25
    if has_title:
        score += 10
    if has_occurred_at:
        score += 10
    if identified:
        score += 15
    return max(0, min(100, score))


def _report_number() -> str:
    return "R-" + secrets.token_hex(3).upper()


async def create_report(
    conn,
    *,
    brand_id: UUID,
    store_id: Optional[UUID],
    link_id: Optional[UUID],
    category: str,
    sentiment: str,
    title: Optional[str],
    description: str,
    occurred_at,
    reporter_account_id: Optional[UUID],
    reporter_contact: Optional[str],
    media: list,
) -> dict:
    """Insert a report + media, score usefulness, and award points if a consumer
    is attached. Returns {report, points_awarded, earned, brand_owner_account_id,
    brand_name, store_name}.

    Wrapped in a transaction so the report + its media + any point award commit
    together (or not at all).
    """
    has_media = bool(media)
    identified = reporter_account_id is not None
    usefulness = score_usefulness(
        description, has_media, bool(title), occurred_at is not None, identified
    )

    async with conn.transaction():
        report = await conn.fetchrow(
            """INSERT INTO tellus_reports
                   (brand_id, store_id, link_id, report_number, category, sentiment,
                    title, description, occurred_at, reporter_account_id, reporter_contact,
                    usefulness_score, status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'new')
               RETURNING *""",
            brand_id, store_id, link_id, _report_number(), category, sentiment,
            title, description, occurred_at, reporter_account_id, reporter_contact, usefulness,
        )
        report_id = report["id"]

        for m in media:
            await conn.execute(
                """INSERT INTO tellus_report_media
                       (report_id, media_type, storage_path, mime_type, file_size, original_filename)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                report_id, m.media_type, m.storage_path, m.mime_type, m.file_size, m.original_filename,
            )

        points_awarded = 0
        if identified:
            # First-ever feedback bonus (one-time).
            prior = await conn.fetchval(
                "SELECT COUNT(*) FROM tellus_reports WHERE reporter_account_id = $1 AND id <> $2",
                reporter_account_id, report_id,
            ) or 0
            if prior == 0:
                r = await award_points(
                    conn, reporter_account_id, "earn_feedback", event_key="first_feedback",
                    reference_type="report", reference_id=f"{report_id}:first_feedback",
                    description="First feedback bonus",
                )
                points_awarded += r["points"]

            # Base usefulness reward.
            if usefulness >= USEFULNESS_THRESHOLD:
                r = await award_points(
                    conn, reporter_account_id, "earn_feedback", event_key="useful_feedback",
                    reference_type="report", reference_id=f"{report_id}:useful_feedback",
                    description="Useful feedback",
                )
                points_awarded += r["points"]

            # Media bonus.
            if has_media:
                r = await award_points(
                    conn, reporter_account_id, "earn_feedback", event_key="feedback_with_media",
                    reference_type="report", reference_id=f"{report_id}:feedback_with_media",
                    description="Feedback with photo/video",
                )
                points_awarded += r["points"]

            # Persist total awarded on the report for the brand view.
            if points_awarded:
                await conn.execute(
                    "UPDATE tellus_reports SET points_awarded = $2 WHERE id = $1",
                    report_id, points_awarded,
                )

        # Brand context for notification/email (owner is an account too).
        brand = await conn.fetchrow(
            "SELECT b.name, b.owner_account_id FROM tellus_brands b WHERE b.id = $1", brand_id
        )
        store_name = None
        if store_id is not None:
            store_name = await conn.fetchval("SELECT name FROM tellus_stores WHERE id = $1", store_id)

        # In-app notification to the brand owner.
        if brand:
            await conn.execute(
                """INSERT INTO tellus_notifications
                       (account_id, kind, title, body, reference_type, reference_id)
                   VALUES ($1, 'feedback', 'New feedback', $2, 'report', $3)""",
                brand["owner_account_id"],
                f"New {sentiment} feedback" + (f" at {store_name}" if store_name else ""),
                str(report_id),
            )

    return {
        "report": dict(report),
        "points_awarded": points_awarded,
        "earned": identified and points_awarded > 0,
        "brand_owner_account_id": brand["owner_account_id"] if brand else None,
        "brand_name": brand["name"] if brand else "",
        "store_name": store_name,
    }
