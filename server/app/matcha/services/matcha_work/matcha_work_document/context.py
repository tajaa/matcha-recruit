"""Compacted context summary read/write for long threads."""
from typing import Optional
from uuid import UUID

from app.database import get_connection


async def get_thread_message_count(thread_id: UUID) -> int:
    """Return total message count for a thread."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM mw_messages WHERE thread_id=$1",
            thread_id,
        )
        return row["cnt"] if row else 0


async def get_context_summary(thread_id: UUID) -> tuple[Optional[str], Optional[int]]:
    """Load the compacted context summary and the message count when it was generated."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT context_summary, context_summary_at_msg_count FROM mw_threads WHERE id=$1",
            thread_id,
        )
        if row and row["context_summary"]:
            return row["context_summary"], row.get("context_summary_at_msg_count")
        return None, None


async def save_context_summary(thread_id: UUID, summary: str, msg_count: int) -> None:
    """Persist a compacted context summary on the thread row."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE mw_threads SET context_summary=$1, context_summary_at_msg_count=$2, updated_at=NOW() WHERE id=$3",
            summary,
            msg_count,
            thread_id,
        )
