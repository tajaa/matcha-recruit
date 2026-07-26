"""mw_elements sync — materializes threads whose state resolves to a skill type."""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.database import get_connection

from ._coerce import _parse_jsonb, _infer_skill_from_state

logger = logging.getLogger(__name__)

VALID_ELEMENT_TYPES = {"offer_letter", "review", "workbook"}


async def list_elements(
    company_id: UUID,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, element_type, title, status, version,
                       linked_offer_letter_id, created_at, updated_at
                FROM mw_elements
                WHERE company_id=$1 AND status=$2 AND is_materialized=true
                ORDER BY updated_at DESC
                LIMIT $3 OFFSET $4
                """,
                company_id,
                status,
                limit,
                offset,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, element_type, title, status, version,
                       linked_offer_letter_id, created_at, updated_at
                FROM mw_elements
                WHERE company_id=$1 AND is_materialized=true
                ORDER BY updated_at DESC
                LIMIT $2 OFFSET $3
                """,
                company_id,
                limit,
                offset,
            )
        return [dict(r) for r in rows]


async def _upsert_element_from_thread_row(conn, thread_row: dict) -> None:
    try:
        state_json = _parse_jsonb(thread_row.get("current_state"))
        inferred_type = _infer_skill_from_state(state_json)
        if inferred_type not in VALID_ELEMENT_TYPES:
            # chat/onboarding threads don't get element records
            return
        existing_is_materialized = await conn.fetchval(
            "SELECT is_materialized FROM mw_elements WHERE thread_id=$1",
            thread_row["id"],
        )
        is_materialized = bool(thread_row.get("linked_offer_letter_id")) or thread_row["status"] == "finalized"
        if thread_row["status"] == "archived" and bool(existing_is_materialized):
            # Keep archived items visible when they were previously materialized.
            is_materialized = True
        await conn.execute(
            """
            INSERT INTO mw_elements(
                thread_id,
                company_id,
                created_by,
                element_type,
                title,
                status,
                state_json,
                version,
                linked_offer_letter_id,
                is_materialized,
                created_at,
                updated_at
            )
            VALUES($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12)
            ON CONFLICT(thread_id) DO UPDATE
            SET
                company_id=EXCLUDED.company_id,
                created_by=EXCLUDED.created_by,
                element_type=EXCLUDED.element_type,
                title=EXCLUDED.title,
                status=EXCLUDED.status,
                state_json=EXCLUDED.state_json,
                version=EXCLUDED.version,
                linked_offer_letter_id=EXCLUDED.linked_offer_letter_id,
                is_materialized=EXCLUDED.is_materialized,
                updated_at=EXCLUDED.updated_at
            """,
            thread_row["id"],
            thread_row["company_id"],
            thread_row["created_by"],
            inferred_type,
            thread_row["title"],
            thread_row["status"],
            json.dumps(state_json),
            thread_row.get("version") or 0,
            thread_row.get("linked_offer_letter_id"),
            is_materialized,
            thread_row.get("created_at"),
            thread_row.get("updated_at") or datetime.now(timezone.utc),
        )
    except Exception as e:
        logger.warning(
            "Failed to upsert mw_elements record for thread %s: %s",
            thread_row.get("id"),
            e,
        )


async def _sync_element_for_thread(conn, thread_id: UUID) -> None:
    try:
        row = await conn.fetchrow(
            """
            SELECT id, company_id, created_by, title, status,
                   current_state, version, linked_offer_letter_id,
                   created_at, updated_at
            FROM mw_threads
            WHERE id=$1
            """,
            thread_id,
        )
        if row is None:
            return
        await _upsert_element_from_thread_row(conn, dict(row))
    except Exception as e:
        logger.warning("Failed to sync mw_elements for thread %s: %s", thread_id, e)


async def sync_element_record(thread_id: UUID) -> None:
    async with get_connection() as conn:
        await _sync_element_for_thread(conn, thread_id)
