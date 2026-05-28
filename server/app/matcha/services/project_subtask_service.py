"""Project subtask service — checklist items under a kanban task.

Subtasks live in `mw_subtasks`, an ordered list of `{title, is_done}` rows scoped
to one `mw_tasks` row (ON DELETE CASCADE). They give a complex feature card an
internal checklist: the board shows "done/total" and a reviewer can re-open
specific items when sending work back.

Tenant isolation: every operation re-verifies the parent task belongs to the
caller's project before touching its subtasks. The route layer has already
verified the user owns the project (`_verify_project_access`); this is
defense-in-depth so a forged task_id can't reach another project's subtasks.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


def _row_to_subtask(row: dict) -> dict:
    d = dict(row)
    for key in ("id", "task_id", "project_id", "company_id", "assigned_to", "created_by"):
        if d.get(key) is not None:
            d[key] = str(d[key])
    for key in ("completed_at", "created_at", "updated_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    return d


async def _task_in_project(conn, task_id: UUID, project_id: UUID) -> Optional[dict]:
    """Return the parent task row (id, company_id) iff it belongs to project_id."""
    return await conn.fetchrow(
        "SELECT id, company_id FROM mw_tasks WHERE id = $1 AND project_id = $2",
        task_id, project_id,
    )


async def _current_round(conn, task_id: UUID) -> int:
    """The task's current round number. Round 1 is the initial work; each
    `round_started` row in mw_task_history opens the next round. So the current
    round = (count of round_started rows) + 1. New checklist items belong to
    this round."""
    started = await conn.fetchval(
        "SELECT COUNT(*) FROM mw_task_history "
        "WHERE task_id = $1 AND event_type = 'round_started'",
        task_id,
    )
    return int(started or 0) + 1


async def list_subtasks(project_id: UUID, task_id: UUID) -> Optional[list[dict]]:
    """Ordered checklist for a task, or None if the task isn't in the project."""
    async with get_connection() as conn:
        if not await _task_in_project(conn, task_id, project_id):
            return None
        rows = await conn.fetch(
            """
            SELECT id, task_id, project_id, company_id, title, is_done, position,
                   round_index, assigned_to, created_by, completed_at,
                   created_at, updated_at
            FROM mw_subtasks
            WHERE task_id = $1
            ORDER BY position ASC, created_at ASC
            """,
            task_id,
        )
    return [_row_to_subtask(dict(r)) for r in rows]


async def create_subtask(
    project_id: UUID,
    task_id: UUID,
    *,
    title: str,
    created_by: Optional[UUID] = None,
    assigned_to: Optional[UUID] = None,
) -> Optional[dict]:
    """Append a checklist item at the end of the task's list. Returns the new
    row, or None if the task isn't in the project. Raises ValueError on a blank
    title.

    Also logs a `subtask_added` row to mw_task_history so the rounds feed in
    the task viewer can attribute each checklist item to who created it and
    when (which round the reviewer added their follow-up items in).
    """
    title = (title or "").strip()
    if not title:
        raise ValueError("Title required")
    async with get_connection() as conn:
        parent = await _task_in_project(conn, task_id, project_id)
        if not parent:
            return None
        # Next position = end of the list (stable append).
        next_pos = await conn.fetchval(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM mw_subtasks WHERE task_id = $1",
            task_id,
        )
        # New items belong to the task's current round, so they sit in the live
        # checklist (which is scoped to the current round) rather than an
        # already-archived past round.
        round_index = await _current_round(conn, task_id)
        row = await conn.fetchrow(
            """
            INSERT INTO mw_subtasks
                (task_id, project_id, company_id, title, position, round_index,
                 assigned_to, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, task_id, project_id, company_id, title, is_done, position,
                      round_index, assigned_to, created_by, completed_at,
                      created_at, updated_at
            """,
            task_id, project_id, parent["company_id"], title, next_pos,
            round_index, assigned_to, created_by,
        )
        # Lazy import dodges the routes→services→routes circular at module
        # load. _log_task_history is best-effort: a logging failure must not
        # roll back the subtask insert.
        from .project_task_service import _log_task_history
        await _log_task_history(
            conn,
            task_id=task_id,
            project_id=project_id,
            actor_user_id=created_by,
            event_type="subtask_added",
            metadata={"title": title, "subtask_id": str(row["id"])},
        )
    return _row_to_subtask(dict(row))


async def update_subtask(
    project_id: UUID,
    task_id: UUID,
    subtask_id: UUID,
    patch: dict,
    *,
    actor_user_id: Optional[UUID] = None,
) -> Optional[dict]:
    """Partial update of one checklist item: is_done (stamps/clears completed_at),
    title, position, assigned_to. Returns the updated row or None if the subtask
    isn't found under that task/project.

    Logs a `subtask_completed` / `subtask_uncompleted` row to mw_task_history
    on an is_done flip (only — title/position/assignee tweaks are too noisy
    for the rounds feed and can stay silent).
    """
    async with get_connection() as conn:
        if not await _task_in_project(conn, task_id, project_id):
            return None

        is_done = patch.get("is_done")
        title = patch.get("title")
        position = patch.get("position")

        completed_at_value = None
        if is_done is True:
            completed_at_value = datetime.now(timezone.utc)

        if title is not None:
            title = title.strip()
            if not title:
                raise ValueError("Title cannot be blank")

        # Snapshot the previous is_done so we can detect a real flip and emit
        # the matching history row. Skipped when the patch isn't toggling
        # is_done — saves the read round-trip.
        previous_is_done: Optional[bool] = None
        if is_done is not None:
            prev = await conn.fetchrow(
                "SELECT is_done, title FROM mw_subtasks WHERE id = $1 AND task_id = $2 AND project_id = $3",
                subtask_id, task_id, project_id,
            )
            if prev is not None:
                previous_is_done = bool(prev["is_done"])

        row = await conn.fetchrow(
            """
            UPDATE mw_subtasks SET
                is_done      = COALESCE($4::boolean, is_done),
                completed_at = CASE
                    WHEN $4::boolean IS TRUE  THEN COALESCE(completed_at, $5::timestamptz)
                    WHEN $4::boolean IS FALSE THEN NULL
                    ELSE completed_at
                END,
                title        = COALESCE($6::text, title),
                position     = COALESCE($7::integer, position),
                assigned_to  = CASE WHEN $8::boolean THEN $9::uuid ELSE assigned_to END,
                updated_at   = NOW()
            WHERE id = $1 AND task_id = $2 AND project_id = $3
            RETURNING id, task_id, project_id, company_id, title, is_done, position,
                      round_index, assigned_to, created_by, completed_at,
                      created_at, updated_at
            """,
            subtask_id, task_id, project_id,
            is_done, completed_at_value, title, position,
            "assigned_to" in patch,
            patch.get("assigned_to"),
        )
        if not row:
            return None

        # Only log a flip — same-value patches (e.g. UI re-asserting state)
        # would otherwise spam the feed.
        if (
            is_done is not None
            and previous_is_done is not None
            and bool(is_done) != previous_is_done
        ):
            from .project_task_service import _log_task_history
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type=("subtask_completed" if is_done else "subtask_uncompleted"),
                metadata={"title": row["title"], "subtask_id": str(row["id"])},
            )
    return _row_to_subtask(dict(row))


async def delete_subtask(
    project_id: UUID,
    task_id: UUID,
    subtask_id: UUID,
    *,
    actor_user_id: Optional[UUID] = None,
) -> bool:
    """Delete one checklist item. Returns True if a row was removed.

    Logs a `subtask_deleted` row to mw_task_history with the title we
    snapshotted right before the delete (so the rounds feed can still
    say "Reviewer removed: 'Validate EIN'" after the row is gone).
    """
    async with get_connection() as conn:
        if not await _task_in_project(conn, task_id, project_id):
            return False
        prev = await conn.fetchrow(
            "SELECT title FROM mw_subtasks WHERE id = $1 AND task_id = $2 AND project_id = $3",
            subtask_id, task_id, project_id,
        )
        title = prev["title"] if prev else None
        result = await conn.execute(
            "DELETE FROM mw_subtasks WHERE id = $1 AND task_id = $2 AND project_id = $3",
            subtask_id, task_id, project_id,
        )
        deleted = result.endswith("1")
        if deleted:
            from .project_task_service import _log_task_history
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="subtask_deleted",
                metadata={"title": title or "", "subtask_id": str(subtask_id)},
            )
    # asyncpg returns a command tag like "DELETE 1".
    return deleted
