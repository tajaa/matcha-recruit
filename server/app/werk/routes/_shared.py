"""Shared helpers for the werk route modules (calls, broadcasts, inbox, job postings).

channels.py / channels_ws.py keep their own copies of these — not touched here.
"""

import asyncio
from uuid import UUID

# NULLIF+BTRIM wrap is load-bearing: Postgres CONCAT() ignores NULL args, so
# with no matching `employees` row CONCAT(NULL, ' ', NULL) returns ' ' — a
# non-NULL string — and COALESCE stops there instead of falling through to
# a.name/u.email. Blanks every admin-only user's name without it.
_USER_NAME_EXPR = "COALESCE(c.name, NULLIF(BTRIM(CONCAT(e.first_name, ' ', e.last_name)), ''), a.name, u.email)"


async def resolve_display_name(conn, user_id: UUID) -> str:
    """Return a display name for a user, falling back to the id if unknown."""
    row = await conn.fetchrow(
        f"""
        SELECT {_USER_NAME_EXPR} AS name
        FROM users u
        LEFT JOIN clients c ON c.user_id = u.id
        LEFT JOIN employees e ON e.user_id = u.id
        LEFT JOIN admins a ON a.user_id = u.id
        WHERE u.id = $1
        """,
        user_id,
    )
    return row["name"] if row and row["name"] else str(user_id)


# Background tasks spawned fire-and-forget from route handlers. Held in a set
# so they aren't GC'd mid-flight (asyncio keeps only a weak ref to running
# tasks) — same pattern as channels_ws.py's _spawn_bg.
_bg_tasks: set = set()


def spawn_bg(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
