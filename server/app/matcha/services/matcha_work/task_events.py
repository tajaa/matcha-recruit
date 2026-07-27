"""Task lifecycle event broadcast — fans a task change out to every
connected member of a project's WebSocket room.

Moved from routes/work/project_ws.py (refactor round 2, stage 3).
"""
import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def broadcast_task_event(project_id: UUID, event: str, payload: dict) -> None:
    """Fan a task lifecycle event out to every connected member of a project room.

    `event` must be one of: "task.created", "task.updated", "task.deleted".
    `payload` is the task row dict (or `{"id": ...}` for delete). Caller stamps
    actor_id so clients can suppress their own optimistic-write echoes.

    Best-effort: any send failure is swallowed by `_broadcast_to_project`'s
    per-conn dead-list handling; callers should still wrap in try/except.
    """
    # Lazy: project_manager is the routes-layer WebSocket connection registry
    # (routes/work/project_ws.py) — a module-level import here would pull
    # services back into routes.
    from app.matcha.routes.work.project_ws import project_manager

    async with project_manager.lock:
        room = list(project_manager.project_rooms.get(project_id, set()))
    logger.info(
        "broadcast %s project=%s room_size=%d members=%s",
        event, project_id, len(room),
        [str(uid) for uid in room],
    )
    await project_manager._broadcast_to_project(project_id, {
        "type": event,
        "project_id": str(project_id),
        "task": payload,
    })
