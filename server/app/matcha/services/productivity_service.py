"""Productivity service — personal kanban boards + cards (`mw_productivity_*`).

User-scoped (no company requirement, so it works for personal Werk users too).
A user owns one or more boards; each card sits in a `todo | in_progress | done`
column. Cards created from a journal text selection back-link to the source via
`source_journal_id` + `source_excerpt`.
"""

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)

COLUMNS = ("todo", "in_progress", "done")


def _col(value: Optional[str]) -> str:
    return value if value in COLUMNS else "todo"


def _parse_board(row) -> dict:
    keys = row.keys()
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "is_default": row["is_default"],
        "status": row["status"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "todo_count": row["todo_count"] if "todo_count" in keys else None,
        "in_progress_count": row["in_progress_count"] if "in_progress_count" in keys else None,
        "done_count": row["done_count"] if "done_count" in keys else None,
    }


def _parse_card(row) -> dict:
    keys = row.keys()
    return {
        "id": str(row["id"]),
        "board_id": str(row["board_id"]),
        "title": row["title"],
        "notes": row["notes"],
        "board_column": row["board_column"],
        "position": row["position"],
        "due_date": row["due_date"].isoformat() if ("due_date" in keys and row["due_date"]) else None,
        "source_journal_id": str(row["source_journal_id"]) if row["source_journal_id"] else None,
        "source_excerpt": row["source_excerpt"],
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


# ── Boards ───────────────────────────────────────────────────────────────


async def list_boards(user_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT b.id, b.title, b.is_default, b.status, b.created_at, b.updated_at,
                   COUNT(*) FILTER (WHERE c.board_column = 'todo')        AS todo_count,
                   COUNT(*) FILTER (WHERE c.board_column = 'in_progress') AS in_progress_count,
                   COUNT(*) FILTER (WHERE c.board_column = 'done')        AS done_count
            FROM mw_productivity_boards b
            LEFT JOIN mw_productivity_cards c ON c.board_id = b.id
            WHERE b.user_id = $1 AND b.status = 'active'
            GROUP BY b.id
            ORDER BY b.is_default DESC, b.created_at ASC
            """,
            user_id,
        )
        return [_parse_board(r) for r in rows]


async def create_board(user_id: UUID, company_id: Optional[UUID], *, title: str) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_productivity_boards (user_id, company_id, title)
            VALUES ($1, $2, COALESCE(NULLIF($3, ''), 'Untitled board'))
            RETURNING id, title, is_default, status, created_at, updated_at
            """,
            user_id, company_id, title,
        )
        return _parse_board(row)


async def _ensure_default_board(conn, user_id: UUID, company_id: Optional[UUID]) -> UUID:
    """The user's default board for quick-capture (journal → to-do). Created on
    first use. Idempotent on (user_id, is_default)."""
    existing = await conn.fetchval(
        "SELECT id FROM mw_productivity_boards WHERE user_id = $1 AND is_default = TRUE AND status = 'active' LIMIT 1",
        user_id,
    )
    if existing is not None:
        return existing
    return await conn.fetchval(
        """
        INSERT INTO mw_productivity_boards (user_id, company_id, title, is_default)
        VALUES ($1, $2, 'My To-Dos', TRUE)
        RETURNING id
        """,
        user_id, company_id,
    )


async def update_board(board_id: UUID, user_id: UUID, patch: dict) -> Optional[dict]:
    async with get_connection() as conn:
        owned = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM mw_productivity_boards WHERE id = $1 AND user_id = $2)",
            board_id, user_id,
        )
        if not owned:
            return None
        sets, params = [], []
        if "title" in patch and patch["title"]:
            params.append(patch["title"])
            sets.append(f"title = ${len(params)}")
        if "status" in patch and patch["status"] in ("active", "archived"):
            params.append(patch["status"])
            sets.append(f"status = ${len(params)}")
        if not sets:
            row = await conn.fetchrow(
                "SELECT id, title, is_default, status, created_at, updated_at FROM mw_productivity_boards WHERE id = $1",
                board_id,
            )
            return _parse_board(row)
        sets.append("updated_at = NOW()")
        params.append(board_id)
        row = await conn.fetchrow(
            f"""
            UPDATE mw_productivity_boards SET {", ".join(sets)}
            WHERE id = ${len(params)}
            RETURNING id, title, is_default, status, created_at, updated_at
            """,
            *params,
        )
        return _parse_board(row)


async def delete_board(board_id: UUID, user_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_productivity_boards WHERE id = $1 AND user_id = $2",
            board_id, user_id,
        )
        return result.endswith("1")


# ── Cards ────────────────────────────────────────────────────────────────


async def _board_owned(conn, board_id: UUID, user_id: UUID) -> bool:
    return await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM mw_productivity_boards WHERE id = $1 AND user_id = $2)",
        board_id, user_id,
    )


async def list_cards(board_id: UUID, user_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        if not await _board_owned(conn, board_id, user_id):
            return []
        rows = await conn.fetch(
            """
            SELECT id, board_id, title, notes, board_column, position,
                   due_date, source_journal_id, source_excerpt, completed_at, created_at, updated_at
            FROM mw_productivity_cards
            WHERE board_id = $1
            ORDER BY board_column, position, created_at
            """,
            board_id,
        )
        return [_parse_card(r) for r in rows]


async def _next_position(conn, board_id: UUID, column: str) -> int:
    return await conn.fetchval(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM mw_productivity_cards WHERE board_id = $1 AND board_column = $2",
        board_id, column,
    )


async def create_card(
    board_id: UUID, user_id: UUID, *,
    title: str, notes: Optional[str] = None, board_column: Optional[str] = None,
    due_date: Optional[date] = None,
    source_journal_id: Optional[UUID] = None, source_excerpt: Optional[str] = None,
) -> Optional[dict]:
    async with get_connection() as conn:
        if not await _board_owned(conn, board_id, user_id):
            return None
        column = _col(board_column)
        pos = await _next_position(conn, board_id, column)
        completed = "NOW()" if column == "done" else "NULL"
        row = await conn.fetchrow(
            f"""
            INSERT INTO mw_productivity_cards
                (board_id, user_id, title, notes, board_column, position,
                 due_date, source_journal_id, source_excerpt, completed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, {completed})
            RETURNING id, board_id, title, notes, board_column, position,
                      due_date, source_journal_id, source_excerpt, completed_at, created_at, updated_at
            """,
            board_id, user_id, title, notes, column, pos, due_date, source_journal_id, source_excerpt,
        )
        return _parse_card(row)


async def quick_todo(
    user_id: UUID, company_id: Optional[UUID], *,
    title: str, due_date: Optional[date] = None,
    source_journal_id: Optional[UUID] = None, source_excerpt: Optional[str] = None,
) -> dict:
    """Ensure the user's default board and drop a new card on it — the
    journal-selection → to-do / calendar path. A `due_date` puts it on the
    calendar too."""
    async with get_connection() as conn:
        board_id = await _ensure_default_board(conn, user_id, company_id)
        pos = await _next_position(conn, board_id, "todo")
        row = await conn.fetchrow(
            """
            INSERT INTO mw_productivity_cards
                (board_id, user_id, title, board_column, position, due_date, source_journal_id, source_excerpt)
            VALUES ($1, $2, $3, 'todo', $4, $5, $6, $7)
            RETURNING id, board_id, title, notes, board_column, position,
                      due_date, source_journal_id, source_excerpt, completed_at, created_at, updated_at
            """,
            board_id, user_id, title, pos, due_date, source_journal_id, source_excerpt,
        )
        return _parse_card(row)


async def update_card(card_id: UUID, user_id: UUID, patch: dict) -> Optional[dict]:
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id, board_id, board_column FROM mw_productivity_cards WHERE id = $1 AND user_id = $2",
            card_id, user_id,
        )
        if existing is None:
            return None
        sets, params = [], []
        if "title" in patch and patch["title"] is not None:
            params.append(patch["title"])
            sets.append(f"title = ${len(params)}")
        if "notes" in patch:
            params.append(patch["notes"])
            sets.append(f"notes = ${len(params)}")
        if "due_date" in patch:
            # Present-but-null clears the date (removes from calendar).
            params.append(patch["due_date"])
            sets.append(f"due_date = ${len(params)}")
        if "board_column" in patch and patch["board_column"] is not None:
            column = _col(patch["board_column"])
            params.append(column)
            sets.append(f"board_column = ${len(params)}")
            # Moving columns appends to the bottom of the target column.
            if column != existing["board_column"]:
                pos = await _next_position(conn, existing["board_id"], column)
                params.append(pos)
                sets.append(f"position = ${len(params)}")
                sets.append("completed_at = " + ("NOW()" if column == "done" else "NULL"))
        elif "position" in patch and patch["position"] is not None:
            params.append(int(patch["position"]))
            sets.append(f"position = ${len(params)}")
        if not sets:
            row = await conn.fetchrow(
                """
                SELECT id, board_id, title, notes, board_column, position,
                       due_date, source_journal_id, source_excerpt, completed_at, created_at, updated_at
                FROM mw_productivity_cards WHERE id = $1
                """,
                card_id,
            )
            return _parse_card(row)
        sets.append("updated_at = NOW()")
        params.append(card_id)
        row = await conn.fetchrow(
            f"""
            UPDATE mw_productivity_cards SET {", ".join(sets)}
            WHERE id = ${len(params)}
            RETURNING id, board_id, title, notes, board_column, position,
                      due_date, source_journal_id, source_excerpt, completed_at, created_at, updated_at
            """,
            *params,
        )
        return _parse_card(row)


async def delete_card(card_id: UUID, user_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_productivity_cards WHERE id = $1 AND user_id = $2",
            card_id, user_id,
        )
        return result.endswith("1")
