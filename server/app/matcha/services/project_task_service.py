"""Project task service — project-scoped kanban tasks for collab projects.

Project tasks live in `mw_tasks` with `project_id` set (null project_id is reserved for
company-wide dashboard tasks surfaced via /tasks). Board state is tracked in
`board_column` (todo|in_progress|review|done). The existing `status` column
(pending|completed|cancelled) stays in sync with `board_column`:
- moving to 'done'   → status='completed', completed_at=now
- moving out of 'done' → status='pending',  completed_at=null
- toggling status complete ↔ moves column to 'done' / 'todo' accordingly
"""

import logging
from datetime import date as _date, datetime, timezone
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


_ALLOWED_COLUMNS = {"todo", "in_progress", "review", "done"}
_ALLOWED_PRIORITIES = {"critical", "high", "medium", "low"}

# Email + bell templates for forward-only column transitions. Destinations
# other than these (e.g. moving back to 'todo') intentionally fire nothing.
_TRANSITION_TEMPLATES: dict[str, dict[str, str]] = {
    "in_progress": {"subject": "Task started: {title}",     "verb": "started"},
    "review":      {"subject": "Ready for review: {title}", "verb": "moved to review"},
    "done":        {"subject": "Task completed: {title}",   "verb": "completed"},
}


async def _broadcast_task_event_safe(project_id: UUID, event: str, payload: dict) -> None:
    """Wrapped broadcast — never fails the caller; logs at warning level.

    Lazy import dodges the routes→services circular at module load time.
    """
    try:
        from ..routes.project_ws import broadcast_task_event
        logger.info("dispatching %s for project=%s", event, project_id)
        await broadcast_task_event(project_id, event, payload)
    except Exception as e:
        logger.warning("Failed to broadcast %s for project %s: %s", event, project_id, e)


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
                   t.completed_at, t.created_at, t.updated_at, t.progress_note,
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
    progress_note: Optional[str] = None,
    project_title: Optional[str] = None,
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
                completed_at, category, progress_note
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'manual', $12)
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column, assigned_to,
                      completed_at, created_at, updated_at, progress_note
            """,
            company_id, created_by, project_id, title.strip(), description,
            due_date, priority, status, board_column, assigned_to,
            completed_at, progress_note,
        )

    if assigned_to is not None and assigned_to != created_by:
        await _notify_task_assigned(
            assigned_to=assigned_to,
            company_id=company_id,
            actor_user_id=created_by,
            project_id=project_id,
            project_title=project_title,
            task_id=row["id"],
            task_title=title.strip(),
        )

    task_payload = _row_to_task(dict(row))
    task_payload["actor_id"] = str(created_by)
    await _broadcast_task_event_safe(project_id, "task.created", task_payload)
    return _row_to_task(dict(row))


async def _notify_task_assigned(
    *,
    assigned_to: UUID,
    company_id: UUID,
    actor_user_id: UUID,
    project_id: UUID,
    project_title: Optional[str],
    task_id: UUID,
    task_title: str,
) -> None:
    """Dispatch a `task_assigned` bell notification + email to the assignee."""
    from . import notification_service as notif_svc

    assigner_name = "Someone"
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT name FROM users WHERE id = $1", actor_user_id
            )
        if row and row["name"]:
            assigner_name = row["name"]
    except Exception as e:
        logger.warning("Failed to look up assigner %s name: %s", actor_user_id, e)

    if project_title:
        body = f"{assigner_name} assigned this to you in {project_title}."
    else:
        body = f"{assigner_name} assigned this to you."

    try:
        await notif_svc.create_notification(
            user_id=assigned_to,
            company_id=company_id,
            type="task_assigned",
            title=f"Assigned: {task_title}",
            body=body,
            link=f"/work?project={project_id}&task={task_id}",
            metadata={
                "project_id": str(project_id),
                "task_id": str(task_id),
                "assigned_by": str(actor_user_id),
            },
            send_email=True,
            email_subject=f"You were assigned: {task_title}",
        )
    except Exception as e:
        logger.warning("Failed to notify task assignment %s -> %s: %s", task_id, assigned_to, e)


async def _notify_task_column_transition(
    *,
    project_id: UUID,
    company_id: UUID,
    actor_user_id: Optional[UUID],
    task_id: UUID,
    task_title: str,
    new_column: str,
    project_title: Optional[str],
) -> None:
    """Email + bell every active project collaborator (minus the actor) when
    a task crosses into in_progress / review / done. Transitions back to
    'todo' (or any other destination) are intentionally silent.
    """
    tpl = _TRANSITION_TEMPLATES.get(new_column)
    if tpl is None:
        return

    from .project_service import list_collaborators
    from . import notification_service as notif_svc

    actor_name = "Someone"
    if actor_user_id is not None:
        try:
            async with get_connection() as conn:
                row = await conn.fetchrow(
                    "SELECT name FROM users WHERE id = $1", actor_user_id
                )
            if row and row["name"]:
                actor_name = row["name"]
        except Exception as e:
            logger.warning("Failed to look up actor %s name: %s", actor_user_id, e)

    try:
        collaborators = await list_collaborators(project_id)
    except Exception as e:
        logger.warning("Failed to load collaborators for project %s: %s", project_id, e)
        return

    recipients = [
        c for c in collaborators
        if actor_user_id is None or c["user_id"] != actor_user_id
    ]
    logger.info(
        "task_progress notify: task=%s project=%s new_column=%s actor=%s "
        "collab_total=%d recipients=%d emails=%s",
        task_id, project_id, new_column, actor_user_id,
        len(collaborators), len(recipients),
        [c["email"] for c in recipients],
    )

    where = f"in {project_title}" if project_title else "in this project"
    body = f"{actor_name} {tpl['verb']} “{task_title}” {where}."
    subject = tpl["subject"].format(title=task_title)
    link = f"/work?project={project_id}&task={task_id}"

    for c in recipients:
        try:
            await notif_svc.create_notification(
                user_id=c["user_id"],
                company_id=company_id,
                type="task_progress",
                title=subject,
                body=body,
                link=link,
                metadata={
                    "project_id": str(project_id),
                    "task_id": str(task_id),
                    "to_column": new_column,
                    "actor_id": str(actor_user_id) if actor_user_id else None,
                },
                send_email=True,
                email_subject=subject,
            )
        except Exception as e:
            logger.warning(
                "Failed task-progress notify task=%s recipient=%s: %s",
                task_id, c["user_id"], e,
            )


async def update_project_task(
    project_id: UUID,
    task_id: UUID,
    patch: dict,
    *,
    actor_user_id: Optional[UUID] = None,
    project_title: Optional[str] = None,
) -> Optional[dict]:
    """Partial update. Enforces status↔board_column sync rules."""
    async with get_connection() as conn:
        current = await conn.fetchrow(
            "SELECT board_column, status, assigned_to, company_id FROM mw_tasks WHERE id = $1 AND project_id = $2",
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

        # Collect simple field updates
        title = patch.get("title")
        description = patch.get("description")
        priority = patch.get("priority")
        due_date = patch.get("due_date")
        assigned_to = patch.get("assigned_to")
        progress_note = patch.get("progress_note")

        if priority is not None and priority not in _ALLOWED_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}")

        # Compute completed_at in Python rather than via a SQL CASE on $3.
        # asyncpg infers each $N's type from how it's used. $3 is assigned to
        # `status` (varchar column) AND compared to text inside the CASE; the
        # previous attempt cast only the CASE site (`$3::text = 'completed'`)
        # but PG saw two contexts demanding different types for the same
        # parameter and raised
        #   AmbiguousParameterError: inconsistent types deduced for $3
        #   DETAIL: text versus character varying
        # Fix: cast at every use of $3 (and $1) so all references are
        # unambiguously text. PG assignment-casts text -> varchar implicitly.
        completed_at_value = (
            datetime.now(timezone.utc) if new_status == "completed" else None
        )

        row = await conn.fetchrow(
            """
            UPDATE mw_tasks SET
                board_column = $1::text,
                status = $3::text,
                completed_at = CASE
                    WHEN $3::text = 'completed' THEN COALESCE(completed_at, $13::timestamptz)
                    ELSE NULL
                END,
                title = COALESCE($4::text, title),
                description = CASE WHEN $5::boolean THEN $6::text ELSE description END,
                priority = COALESCE($7::text, priority),
                due_date = CASE WHEN $8::boolean THEN $9::date ELSE due_date END,
                assigned_to = CASE WHEN $10::boolean THEN $11::uuid ELSE assigned_to END,
                progress_note = CASE WHEN $14::boolean THEN $15::text ELSE progress_note END,
                updated_at = NOW()
            WHERE id = $2 AND project_id = $12
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column, assigned_to,
                      completed_at, created_at, updated_at, progress_note
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
            completed_at_value,           # $13
            "progress_note" in patch,     # $14
            progress_note,                # $15
        )

    if row and "assigned_to" in patch:
        new_assignee = row["assigned_to"]
        old_assignee = current["assigned_to"]
        if (
            new_assignee is not None
            and new_assignee != old_assignee
            and new_assignee != actor_user_id
        ):
            await _notify_task_assigned(
                assigned_to=new_assignee,
                company_id=current["company_id"],
                actor_user_id=actor_user_id or new_assignee,
                project_id=project_id,
                project_title=project_title,
                task_id=task_id,
                task_title=row["title"],
            )

    if row and new_column != current["board_column"]:
        await _notify_task_column_transition(
            project_id=project_id,
            company_id=current["company_id"],
            actor_user_id=actor_user_id,
            task_id=task_id,
            task_title=row["title"],
            new_column=new_column,
            project_title=project_title,
        )

    if row:
        task_payload = _row_to_task(dict(row))
        if actor_user_id is not None:
            task_payload["actor_id"] = str(actor_user_id)
        await _broadcast_task_event_safe(project_id, "task.updated", task_payload)

    return _row_to_task(dict(row)) if row else None


async def delete_project_task(
    project_id: UUID, task_id: UUID, *, actor_user_id: Optional[UUID] = None
) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
    deleted = result.endswith(" 1")
    if deleted:
        payload: dict = {"id": str(task_id)}
        if actor_user_id is not None:
            payload["actor_id"] = str(actor_user_id)
        await _broadcast_task_event_safe(project_id, "task.deleted", payload)
    return deleted


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
