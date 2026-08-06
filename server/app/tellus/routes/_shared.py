"""Shared helpers for Tell-Us routes — ownership checks + media URL minting."""
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status

from ...core.services.storage import get_storage
from ..models.tellus import TellusReport, TellusReportAnswer, TellusReportMedia

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_SLUG_MAX_LEN = 60


def slugify(name: str) -> str:
    """Mirrors the SQL slugify in tellus_app_05 (used for new brand signups —
    the migration's set-based backfill handles pre-existing rows). Order
    matters for the two to agree: strip specials -> trim both ends -> cut to
    _SLUG_MAX_LEN -> trim the trailing dash a mid-cut can leave behind."""
    base = _SLUG_STRIP_RE.sub("-", (name or "").lower()).strip("-")
    base = base[:_SLUG_MAX_LEN].rstrip("-")
    return base or "brand"


def effective_review_state(row) -> Optional[str]:
    """'held' + publish_at in the past -> 'published' (derived, never stored —
    see tellus_app_05 docstring for why). Anything else (withdrawn, or no
    review_state column/value at all) passes through unchanged."""
    state = row["review_state"] if "review_state" in row.keys() else None
    if state == "held":
        publish_at = row["publish_at"]
        if publish_at is not None and publish_at <= datetime.now(timezone.utc):
            return "published"
    return state


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


def _answer_rows_to_models(arows) -> list[TellusReportAnswer]:
    return [
        TellusReportAnswer(id=a["id"], prompt_text=a["prompt_text"], answer=a["answer"], position=a["position"])
        for a in arows
    ]


def _build_report(row, *, store_name, media, has_dm_thread, answers=()) -> TellusReport:
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
        reward_status=row["reward_status"] if "reward_status" in row.keys() else None,
        points_awarded=row["points_awarded"] if "points_awarded" in row.keys() else 0,
        created_at=row["created_at"],
        media=media,
        rating=row["rating"] if "rating" in row.keys() else None,
        review_state=effective_review_state(row),
        publish_at=row["publish_at"] if "publish_at" in row.keys() else None,
        hearted_at=row["hearted_at"] if "hearted_at" in row.keys() else None,
        brand_public_reply=row["brand_public_reply"] if "brand_public_reply" in row.keys() else None,
        brand_public_reply_at=row["brand_public_reply_at"] if "brand_public_reply_at" in row.keys() else None,
        is_identified=row["reporter_account_id"] is not None,
        has_dm_thread=has_dm_thread,
        answers=list(answers),
    )


def _media_rows_to_models(mrows) -> list[TellusReportMedia]:
    return [
        TellusReportMedia(
            id=m["id"],
            media_type=m["media_type"],
            mime_type=m["mime_type"],
            original_filename=m["original_filename"],
            url=_media_url(m["storage_path"]),
        )
        for m in mrows
    ]


async def serialize_report(conn, row, *, include_media: bool = True) -> TellusReport:
    """Row → TellusReport, minting presigned media URLs at read time. For a
    list of rows use serialize_reports instead — this issues 3 queries per
    call, fine for the single-row mutation-response case this is meant for."""
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
        media = _media_rows_to_models(mrows)

    has_dm_thread = bool(await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM tellus_dm_threads WHERE report_id = $1)", row["id"]
    ))

    arows = await conn.fetch(
        "SELECT id, prompt_text, answer, position FROM tellus_report_answers WHERE report_id = $1 ORDER BY position",
        row["id"],
    )

    return _build_report(
        row, store_name=store_name, media=media, has_dm_thread=has_dm_thread,
        answers=_answer_rows_to_models(arows),
    )


async def serialize_reports(conn, rows: list) -> list[TellusReport]:
    """Batched sibling of serialize_report for list endpoints — one query per
    lookup (store names, media, DM-thread existence) instead of one per row."""
    if not rows:
        return []

    report_ids = [r["id"] for r in rows]
    store_ids = [r["store_id"] for r in rows if r["store_id"] is not None]

    store_names: dict = {}
    if store_ids:
        srows = await conn.fetch("SELECT id, name FROM tellus_stores WHERE id = ANY($1::uuid[])", store_ids)
        store_names = {s["id"]: s["name"] for s in srows}

    mrows = await conn.fetch(
        "SELECT id, report_id, media_type, mime_type, original_filename, storage_path "
        "FROM tellus_report_media WHERE report_id = ANY($1::uuid[]) ORDER BY created_at",
        report_ids,
    )
    media_by_report: dict = {}
    for m in mrows:
        media_by_report.setdefault(m["report_id"], []).append(m)

    dm_rows = await conn.fetch(
        "SELECT DISTINCT report_id FROM tellus_dm_threads WHERE report_id = ANY($1::uuid[])", report_ids
    )
    has_dm_set = {d["report_id"] for d in dm_rows}

    arows = await conn.fetch(
        "SELECT id, report_id, prompt_text, answer, position FROM tellus_report_answers "
        "WHERE report_id = ANY($1::uuid[]) ORDER BY report_id, position", report_ids,
    )
    answers_by_report: dict = {}
    for a in arows:
        answers_by_report.setdefault(a["report_id"], []).append(a)

    return [
        _build_report(
            r,
            store_name=store_names.get(r["store_id"]),
            media=_media_rows_to_models(media_by_report.get(r["id"], [])),
            has_dm_thread=r["id"] in has_dm_set,
            answers=_answer_rows_to_models(answers_by_report.get(r["id"], [])),
        )
        for r in rows
    ]
