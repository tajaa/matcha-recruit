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


async def list_subtasks(project_id: UUID, task_id: UUID) -> Optional[list[dict]]:
    """Ordered checklist for a task, or None if the task isn't in the project."""
    async with get_connection() as conn:
        if not await _task_in_project(conn, task_id, project_id):
            return None
        rows = await conn.fetch(
            """
            SELECT id, task_id, project_id, company_id, title, is_done, position,
                   assigned_to, created_by, completed_at, created_at, updated_at
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
    title."""
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
        row = await conn.fetchrow(
            """
            INSERT INTO mw_subtasks
                (task_id, project_id, company_id, title, position, assigned_to, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, task_id, project_id, company_id, title, is_done, position,
                      assigned_to, created_by, completed_at, created_at, updated_at
            """,
            task_id, project_id, parent["company_id"], title, next_pos,
            assigned_to, created_by,
        )
    return _row_to_subtask(dict(row))


async def update_subtask(
    project_id: UUID,
    task_id: UUID,
    subtask_id: UUID,
    patch: dict,
) -> Optional[dict]:
    """Partial update of one checklist item: is_done (stamps/clears completed_at),
    title, position, assigned_to. Returns the updated row or None if the subtask
    isn't found under that task/project."""
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
                      assigned_to, created_by, completed_at, created_at, updated_at
            """,
            subtask_id, task_id, project_id,
            is_done, completed_at_value, title, position,
            "assigned_to" in patch,
            patch.get("assigned_to"),
        )
    if not row:
        return None
    return _row_to_subtask(dict(row))


async def delete_subtask(
    project_id: UUID,
    task_id: UUID,
    subtask_id: UUID,
) -> bool:
    """Delete one checklist item. Returns True if a row was removed."""
    async with get_connection() as conn:
        if not await _task_in_project(conn, task_id, project_id):
            return False
        result = await conn.execute(
            "DELETE FROM mw_subtasks WHERE id = $1 AND task_id = $2 AND project_id = $3",
            subtask_id, task_id, project_id,
        )
    # asyncpg returns a command tag like "DELETE 1".
    return result.endswith("1")
