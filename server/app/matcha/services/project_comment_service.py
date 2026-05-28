"""Project note (section) comment service.

In-app comments on project notes. Notes are entries in the `mw_projects.sections`
JSONB array, keyed by a short hex string id (not a UUID), so `section_id` is a
plain string here. Comments live in `mw_section_comments`.

Tenant isolation: the route layer verifies the caller can access the project
(`_verify_project_access`) before reaching here; every query is additionally
scoped by `company_id` as defense-in-depth.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


def _row_to_comment(row: dict) -> dict:
    d = dict(row)
    for key in ("id", "project_id", "user_id", "reply_to_comment_id"):
        if d.get(key) is not None:
            d[key] = str(d[key])
    for key in ("created_at", "updated_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    return d


async def list_section_comments(project_id: UUID, section_id: str) -> list[dict]:
    """All comments on a note, oldest first, with resolved author name + avatar."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.project_id, c.section_id, c.user_id, c.content,
                   c.reply_to_comment_id, c.created_at, c.updated_at,
                   COALESCE(a.name, u.email) AS author_name,
                   u.avatar_url
            FROM mw_section_comments c
            JOIN users u ON u.id = c.user_id
            LEFT JOIN admins a ON a.user_id = c.user_id
            WHERE c.project_id = $1 AND c.section_id = $2
            ORDER BY c.created_at ASC
            """,
            project_id, section_id,
        )
    return [_row_to_comment(r) for r in rows]


async def create_section_comment(
    *,
    project_id: UUID,
    section_id: str,
    company_id: UUID,
    user_id: UUID,
    content: str,
    reply_to_comment_id: Optional[UUID] = None,
) -> dict:
    """Insert a comment and return it with the author's name + avatar resolved."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_section_comments
                (project_id, section_id, company_id, user_id, content, reply_to_comment_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, project_id, section_id, user_id, content,
                      reply_to_comment_id, created_at, updated_at
            """,
            project_id, section_id, company_id, user_id, content, reply_to_comment_id,
        )
        author = await conn.fetchrow(
            """
            SELECT COALESCE(a.name, u.email) AS author_name, u.avatar_url
            FROM users u
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id = $1
            """,
            user_id,
        )
    out = _row_to_comment(row)
    out["author_name"] = author["author_name"] if author else None
    out["avatar_url"] = author["avatar_url"] if author else None
    return out


async def delete_section_comment(comment_id: UUID, user_id: UUID) -> bool:
    """Delete a comment. Author-only; returns False if not found / not the author."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_section_comments WHERE id = $1 AND user_id = $2",
            comment_id, user_id,
        )
    # asyncpg returns e.g. "DELETE 1" / "DELETE 0".
    return result.rsplit(" ", 1)[-1] != "0"


async def get_comment_author(comment_id: UUID) -> Optional[UUID]:
    """Author user_id of a comment (for notifying a parent-comment author)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM mw_section_comments WHERE id = $1", comment_id
        )
    return row["user_id"] if row else None
