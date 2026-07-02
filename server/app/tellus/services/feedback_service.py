"""Tell-Us feedback intake + usefulness → points.

Creates a report (+ its media rows), scores how *useful* the feedback is, and
credits points per the brand's reward_mode:
  - auto   — an identified consumer's useful feedback credits immediately
  - manual — the report lands with reward_status='pending'; the brand's
             approve/reject decision (routes/feedback.py) drives the credit

Anonymous feedback always lands; it just earns 0 (reward_status NULL — there is
nobody to credit). `award_for_report` is idempotent (ledger reference ids), so
re-running it — approval retries, races — can never double-credit.
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


async def award_for_report(conn, report: dict, *, bypass_cooldown: bool = False) -> int:
    """Credit every earning rule this report qualifies for. Returns the total
    points actually awarded this call (0 on idempotent replay).

    Used by both the auto path (at submission) and the manual path (at brand
    approval). Each rule's ledger reference id makes it once-only:
      - first_feedback  → once per ACCOUNT ever ("first_feedback:{account_id}")
      - useful_feedback / feedback_with_media → once per report
    """
    account_id = report["reporter_account_id"]
    if account_id is None:
        return 0
    report_id = report["id"]

    total = 0
    r = await award_points(
        conn, account_id, "earn_feedback", event_key="first_feedback",
        reference_type="account", reference_id=f"first_feedback:{account_id}",
        description="First feedback bonus", bypass_cooldown=bypass_cooldown,
    )
    total += r["points"]

    if (report["usefulness_score"] or 0) >= USEFULNESS_THRESHOLD:
        r = await award_points(
            conn, account_id, "earn_feedback", event_key="useful_feedback",
            reference_type="report", reference_id=f"{report_id}:useful_feedback",
            description="Useful feedback", bypass_cooldown=bypass_cooldown,
        )
        total += r["points"]

    has_media = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM tellus_report_media WHERE report_id = $1)", report_id
    )
    if has_media:
        r = await award_points(
            conn, account_id, "earn_feedback", event_key="feedback_with_media",
            reference_type="report", reference_id=f"{report_id}:feedback_with_media",
            description="Feedback with photo/video", bypass_cooldown=bypass_cooldown,
        )
        total += r["points"]

    if total:
        await conn.execute(
            "UPDATE tellus_reports SET points_awarded = points_awarded + $2, updated_at = NOW() "
            "WHERE id = $1",
            report_id, total,
        )
    return total


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
    """Insert a report + media, score usefulness, and credit or queue points per
    the brand's reward_mode. Returns {report, points_awarded, earned,
    reward_pending, brand_owner_account_id, brand_name, store_name}.

    Wrapped in a transaction so the report + its media + any point award commit
    together (or not at all).
    """
    has_media = bool(media)
    identified = reporter_account_id is not None
    usefulness = score_usefulness(
        description, has_media, bool(title), occurred_at is not None, identified
    )

    async with conn.transaction():
        brand = await conn.fetchrow(
            "SELECT name, owner_account_id, reward_mode FROM tellus_brands WHERE id = $1",
            brand_id,
        )
        manual = bool(brand and brand["reward_mode"] == "manual")

        # NULL for anonymous (nothing to credit); manual → queue for the brand;
        # auto → credited right below, so it lands approved.
        reward_status = None if not identified else ("pending" if manual else "approved")

        report = await conn.fetchrow(
            """INSERT INTO tellus_reports
                   (brand_id, store_id, link_id, report_number, category, sentiment,
                    title, description, occurred_at, reporter_account_id, reporter_contact,
                    usefulness_score, status, reward_status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'new', $13)
               RETURNING *""",
            brand_id, store_id, link_id, _report_number(), category, sentiment,
            title, description, occurred_at, reporter_account_id, reporter_contact,
            usefulness, reward_status,
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
        if identified and not manual:
            points_awarded = await award_for_report(conn, dict(report))

        store_name = None
        if store_id is not None:
            store_name = await conn.fetchval("SELECT name FROM tellus_stores WHERE id = $1", store_id)

        # In-app notification to the brand owner (flag the pending decision).
        if brand:
            note = f"New {sentiment} feedback" + (f" at {store_name}" if store_name else "")
            if reward_status == "pending":
                note += " — reward approval needed"
            await conn.execute(
                """INSERT INTO tellus_notifications
                       (account_id, kind, title, body, reference_type, reference_id)
                   VALUES ($1, 'feedback', 'New feedback', $2, 'report', $3)""",
                brand["owner_account_id"], note, str(report_id),
            )

    return {
        "report": dict(report),
        "points_awarded": points_awarded,
        "earned": identified and points_awarded > 0,
        "reward_pending": reward_status == "pending",
        "brand_owner_account_id": brand["owner_account_id"] if brand else None,
        "brand_name": brand["name"] if brand else "",
        "store_name": store_name,
    }
