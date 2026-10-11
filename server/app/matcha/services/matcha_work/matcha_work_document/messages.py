"""Thread message read/write."""
import json
from typing import Optional
from uuid import UUID

from app.database import get_connection


async def get_thread_messages(thread_id: UUID, limit: int | None = None) -> list[dict]:
    async with get_connection() as conn:
        if limit is not None:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, role, content, version_created, metadata, created_at
                FROM (
                    SELECT id, thread_id, role, content, version_created, metadata, created_at
                    FROM mw_messages
                    WHERE thread_id=$1
                    ORDER BY created_at DESC
                    LIMIT $2
                ) recent_messages
                ORDER BY created_at ASC
                """,
                thread_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, role, content, version_created, metadata, created_at
                FROM mw_messages
                WHERE thread_id=$1
                ORDER BY created_at ASC
                """,
                thread_id,
            )
        return [dict(r) for r in rows]


async def get_thread_messages_from(thread_id: UUID, offset: int) -> list[dict]:
    """Messages from the `offset`-th (0-based, oldest first) to the newest.

    Ordered by (created_at, id) so an index means the same message on every
    turn: a Claude thread's history window starts at a fixed index
    (`_claude_thread.claude_history_start`) and must not shift under ties."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, thread_id, role, content, version_created, metadata, created_at
            FROM mw_messages
            WHERE thread_id=$1
            ORDER BY created_at ASC, id ASC
            OFFSET $2
            """,
            thread_id,
            max(0, offset),
        )
        return [dict(r) for r in rows]


async def add_message(
    thread_id: UUID,
    role: str,
    content: str,
    version_created: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_messages(thread_id, role, content, version_created, metadata)
            VALUES($1, $2, $3, $4, $5::jsonb)
            RETURNING id, thread_id, role, content, version_created, metadata, created_at
            """,
            thread_id,
            role,
            content,
            version_created,
            json.dumps(metadata) if metadata else None,
        )
        await conn.execute(
            "UPDATE mw_threads SET updated_at = NOW() WHERE id = $1",
            thread_id,
        )
        return dict(row)
