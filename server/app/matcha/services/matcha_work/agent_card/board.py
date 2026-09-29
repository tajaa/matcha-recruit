"""Worker-safe kanban writes for agent cards.

`project_task_service` goes through the API's connection pool, which a Celery
worker does not have, so the few card writes a run makes live here on
`connection_or_direct()`. Column moves are conditional: a card the person
dragged somewhere else mid-run is never yanked back — the result is still
stored on the run and shows up whenever they open the card.

Board updates reach open clients through the same Redis channel the API's
project WebSocket subscribers already listen on (`projects:fanout`).
"""
from __future__ import annotations

import json
import logging
import os
import time
from uuid import UUID

from app.database import connection_or_direct
from app.matcha.services.matcha_work.project_task_service import (
    _log_task_history,
    _row_to_task,
)

logger = logging.getLogger(__name__)

FANOUT_CHANNEL = "projects:fanout"
_PROGRESS_MIN_INTERVAL = 3.0
_last_progress: dict[UUID, float] = {}

_TASK_COLUMNS = """id, project_id, company_id, created_by, title, description,
    due_date, priority, status, board_column,
    COALESCE(pipeline_column, 'lead') AS pipeline_column,
    assigned_to, completed_at, created_at, updated_at,
    progress_note, category, element_id, review_note"""


async def publish_task_updated(project_id: UUID, task_row: dict) -> None:
    """Fan a `task.updated` out to every API worker's project sockets."""
    envelope = {
        "kind": "project",
        "project_id": str(project_id),
        "exclude_user": None,
        "message": {
            "type": "task.updated",
            "project_id": str(project_id),
            "task": {**_row_to_task(task_row), "actor_id": None},
        },
    }
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        try:
            await client.publish(FANOUT_CHANNEL, json.dumps(envelope, default=str))
        finally:
            await client.aclose()
    except Exception:
        # Best effort: the board still reads the truth on its next fetch.
        logger.warning("agent card fanout failed project=%s", project_id, exc_info=True)


async def _move(task_id: UUID, *, to: str, from_columns: tuple[str, ...], run_id: UUID) -> dict | None:
    async with connection_or_direct() as conn, conn.transaction():
        before = await conn.fetchval(
            "SELECT board_column FROM mw_tasks WHERE id = $1 FOR UPDATE", task_id,
        )
        if before not in from_columns:
            return None
        row = await conn.fetchrow(
            f"""UPDATE mw_tasks
                    SET board_column = $2, status = 'pending', completed_at = NULL,
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING {_TASK_COLUMNS}""",
            task_id, to,
        )
        await _log_task_history(
            conn,
            task_id=task_id,
            project_id=row["project_id"],
            actor_user_id=None,
            event_type="column_change",
            from_value=before,
            to_value=to,
            metadata={"agent_run_id": str(run_id), "actor": "espresso_agent"},
        )
    return dict(row)


async def claim_column(task_id: UUID, *, run_id: UUID) -> dict | None:
    """todo → in_progress when the card is in To do, whatever the round.

    A revision round normally starts from Changes requested, which is already
    "the agent is fixing it" — that case is a no-op. But a rerun of round N≥2
    from To do (or a card moved back by hand) must still leave To do, or it
    would finish without ever passing through In progress.
    """
    return await _move(task_id, to="in_progress", from_columns=("todo",), run_id=run_id)


async def finish_column(task_id: UUID, *, run_id: UUID) -> dict | None:
    return await _move(
        task_id, to="review", from_columns=("in_progress", "changes_requested"), run_id=run_id,
    )


async def set_progress(task_id: UUID, note: str, *, force: bool = False) -> dict | None:
    """Live status line on the card, throttled so a busy run can't spam writes."""
    now = time.monotonic()
    if not force and now - _last_progress.get(task_id, 0.0) < _PROGRESS_MIN_INTERVAL:
        return None
    _last_progress[task_id] = now
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"""UPDATE mw_tasks SET progress_note = $2, updated_at = NOW()
                WHERE id = $1 RETURNING {_TASK_COLUMNS}""",
            task_id, note[:500],
        )
    return dict(row) if row else None
