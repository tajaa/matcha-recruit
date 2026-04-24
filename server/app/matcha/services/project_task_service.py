"""Project task service — project-scoped kanban tasks for collab projects.

Project tasks live in `mw_tasks` with `project_id` set (null project_id is reserved for
company-wide dashboard tasks surfaced via /tasks). Board state is tracked in
`board_column` (todo|in_progress|review|done). The existing `status` column
(pending|completed|cancelled) stays in sync with `board_column`:
- moving to 'done'   → status='completed', completed_at=now
- moving out of 'done' → status='pending',  completed_at=null
- toggling status complete ↔ moves column to 'done' / 'todo' accordingly
"""

from datetime import date as _date, datetime, timezone
from typing import Optional
from uuid import UUID

from ...database import get_connection


_ALLOWED_COLUMNS = {"todo", "in_progress", "review", "done"}
_ALLOWED_PRIORITIES = {"critical", "high", "medium", "low"}


def _row_to_task(row: dict) -> dict:
    d = dict(row)
    for key in ("id", "project_id", "created_by", "assigned_to"):
        if d.get(key) is not None:
            d[key] = str(d[key])
    if d.get("due_date") is not None:
        d["due_date"] = d["due_date"].isoformat()
    for key in ("completed_at", "created_at", "updated_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    return d


async def list_project_tasks(project_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.project_id, t.company_id, t.created_by, t.title, t.description,
                   t.due_date, t.priority, t.status, t.board_column, t.assigned_to,
                   t.completed_at, t.created_at, t.updated_at,
                   COALESCE(a.name, u.email) AS assigned_name
            FROM mw_tasks t
            LEFT JOIN users u ON u.id = t.assigned_to
            LEFT JOIN admins a ON a.user_id = t.assigned_to
            WHERE t.project_id = $1 AND t.status != 'cancelled'
            ORDER BY
                CASE t.priority
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4
                END,
                t.created_at DESC
            """,
            project_id,
        )
    return [_row_to_task(dict(r)) for r in rows]


async def create_project_task(
    *,
    project_id: UUID,
    company_id: UUID,
    created_by: UUID,
    title: str,
    description: Optional[str] = None,
    board_column: str = "todo",
    priority: str = "medium",
    due_date: Optional[_date] = None,
    assigned_to: Optional[UUID] = None,
) -> dict:
    if board_column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Invalid board_column: {board_column}")
    if priority not in _ALLOWED_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority}")
    if not title or not title.strip():
        raise ValueError("Title required")

    status = "completed" if board_column == "done" else "pending"
    completed_at = datetime.now(timezone.utc) if status == "completed" else None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_tasks (
                company_id, created_by, project_id, title, description,
                due_date, priority, status, board_column, assigned_to,
                completed_at, category
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'manual')
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column, assigned_to,
                      completed_at, created_at, updated_at
            """,
            company_id, created_by, project_id, title.strip(), description,
            due_date, priority, status, board_column, assigned_to,
            completed_at,
        )
    return _row_to_task(dict(row))


async def update_project_task(project_id: UUID, task_id: UUID, patch: dict) -> Optional[dict]:
    """Partial update. Enforces status↔board_column sync rules."""
    async with get_connection() as conn:
        current = await conn.fetchrow(
            "SELECT board_column, status FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
        if not current:
            return None

        # Resolve target column + status with sync rules
        new_column = patch.get("board_column", current["board_column"])
        new_status = patch.get("status", current["status"])

        if "board_column" in patch:
            if new_column not in _ALLOWED_COLUMNS:
                raise ValueError(f"Invalid board_column: {new_column}")
            if new_column == "done":
                new_status = "completed"
            elif current["board_column"] == "done":
                new_status = "pending"

        if "status" in patch:
            if new_status not in ("pending", "completed", "cancelled"):
                raise ValueError(f"Invalid status: {new_status}")
            if new_status == "completed" and new_column != "done":
                new_column = "done"
            elif new_status == "pending" and new_column == "done":
                new_column = "todo"

        completed_at_expr = "CASE WHEN $3 = 'completed' THEN COALESCE(completed_at, NOW()) ELSE NULL END"

        # Collect simple field updates
        title = patch.get("title")
        description = patch.get("description")
        priority = patch.get("priority")
        due_date = patch.get("due_date")
        assigned_to = patch.get("assigned_to")

        if priority is not None and priority not in _ALLOWED_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}")

        row = await conn.fetchrow(
            f"""
            UPDATE mw_tasks SET
                board_column = $1,
                status = $3,
                completed_at = {completed_at_expr},
                title = COALESCE($4, title),
                description = CASE WHEN $5::boolean THEN $6 ELSE description END,
                priority = COALESCE($7, priority),
                due_date = CASE WHEN $8::boolean THEN $9 ELSE due_date END,
                assigned_to = CASE WHEN $10::boolean THEN $11 ELSE assigned_to END,
                updated_at = NOW()
            WHERE id = $2 AND project_id = $12
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column, assigned_to,
                      completed_at, created_at, updated_at
            """,
            new_column,                   # $1
            task_id,                      # $2
            new_status,                   # $3
            title,                        # $4
            "description" in patch,       # $5
            description,                  # $6
            priority,                     # $7
            "due_date" in patch,          # $8
            due_date,                     # $9
            "assigned_to" in patch,       # $10
            assigned_to,                  # $11
            project_id,                   # $12
        )
    return _row_to_task(dict(row)) if row else None


async def delete_project_task(project_id: UUID, task_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
    return result.endswith(" 1")


async def mark_project_complete(project_id: UUID) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE mw_projects SET status = 'completed', updated_at = NOW()
            WHERE id = $1
            RETURNING id, status, updated_at
            """,
            project_id,
        )
    if not row:
        raise ValueError("Project not found")
    d = dict(row)
    d["id"] = str(d["id"])
    if d.get("updated_at") is not None:
        d["updated_at"] = d["updated_at"].isoformat()
    return d
