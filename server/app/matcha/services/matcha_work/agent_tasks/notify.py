"""Telling the person a task finished, stopped, or needs them.

The bell row plus the live push (`notification_service.create_notification`,
on the caller's connection so it works in the worker; the push goes through
Redis). Best effort: a notification that fails never fails the task.
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.database import decode_jsonb

logger = logging.getLogger(__name__)


def link_for(task_id: UUID | str) -> str:
    return f"/espresso/tasks/{task_id}"


def message_for(task: dict) -> tuple[str, str, str] | None:
    """(type, title, body) for a task that just stopped, or None when the
    person needs no telling (they cancelled it themselves)."""
    name = (task.get("title") or task.get("directive") or "Your task")[:80]
    progress = decode_jsonb(task.get("progress"), {}) or {}
    status = task.get("status")
    if status == "done":
        return "agent_task_done", f"Done: {name}", str(progress.get("note") or "See what it found.")[:300]
    if status == "failed":
        return "agent_task_done", f"Stopped: {name}", str(task.get("error") or progress.get("note") or "")[:300]
    if status == "waiting":
        needs = decode_jsonb(task.get("needs"), {}) or {}
        return "agent_task_needs_you", f"Needs you: {name}", str(needs.get("prompt") or "Espresso needs an answer to go on.")[:300]
    return None


async def tell(conn, task: dict) -> None:
    """The notification for a task that just stopped, as Tasks shows it (a job
    search's pointer already carries its search's state). Raises."""
    message = message_for(task)
    if message is None:
        return
    kind, title, body = message
    from app.matcha.services import notification_service

    task_id = task["id"]
    await notification_service.create_notification(
        user_id=task["user_id"], company_id=task["company_id"], type=kind, title=title, body=body,
        link=link_for(task_id),
        # Strings only (the Mac decodes metadata as [String: String]);
        # `agent_task_id` because `task_id` is a kanban card there.
        metadata={"agent_task_id": str(task_id), "task_id": str(task_id), "playbook": task["playbook"],
                  "status": task["status"]},
        conn=conn,
    )


async def task_stopped(conn, task_id: UUID) -> None:
    try:
        row = await conn.fetchrow(
            """SELECT id, user_id, company_id, playbook, title, directive, status, progress, error, needs
               FROM mw_agent_tasks WHERE id = $1 AND deleted_at IS NULL""",
            task_id,
        )
        if row is not None:
            await tell(conn, dict(row))
    except Exception:
        logger.warning("task notification failed task=%s", task_id, exc_info=True)
