"""Attribution context for the requirement-version trigger (migration jrver01).

The `capture_requirement_version` trigger fires on EVERY write to
`jurisdiction_requirements`, so history is captured whether or not a caller
labels it. This helper only adds the *attribution* — who/what caused the change —
by setting two session GUCs the trigger reads via `current_setting(..., true)`.

Scope matches the existing tenant/user GUCs in `database.get_connection`:
session-level `set_config(..., false)`, cleared by asyncpg's `RESET ALL` when the
connection returns to the pool (and by any explicit reset a block does). Call it
right before the write, on the same connection.
"""
from typing import Optional


async def set_change_context(conn, source: str, actor_id: Optional[object] = None) -> None:
    """Label the next requirement write(s) on ``conn`` with ``source`` + optional actor.

    ``source`` is a short tag ('admin_edit', 'approve', 'codify', 'research', …).
    ``actor_id`` is the admin/user UUID (or None). Both are best-effort: an
    unlabeled write still captures a version, just without provenance.
    """
    await conn.execute(
        "SELECT set_config('app.change_source', $1, false), "
        "       set_config('app.actor_id', $2, false)",
        source or "",
        str(actor_id) if actor_id else "",
    )
