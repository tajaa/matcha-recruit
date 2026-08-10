"""Persistence and repo reads for the collab-code agent.

Every DB operation uses ``connection_or_direct`` so this module is safe from
the pool-free Celery worker as well as the ASGI process.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from app.database import connection_or_direct
from app.matcha.services.matcha_work import element_repo_service
from app.matcha.services.matcha_work.github_service import GITHUB_API, GitHubError, _headers, _token

logger = logging.getLogger(__name__)


async def mark_run(run_id: UUID, *, status: str, **values: Any) -> None:
    assignments = ["status = $2", "completed_at = CASE WHEN $2 IN ('done', 'failed') THEN NOW() ELSE completed_at END"]
    params: list[Any] = [run_id, status]
    for column in ("task_id", "branch", "pr_url", "error", "model_calls", "files_changed", "token_usage"):
        if column in values:
            assignments.append(f"{column} = ${len(params) + 1}" + ("::jsonb" if column == "token_usage" else ""))
            value = json.dumps(values[column]) if column == "token_usage" else values[column]
            params.append(value)
    async with connection_or_direct() as conn:
        await conn.execute(f"UPDATE huume_code_runs SET {', '.join(assignments)} WHERE id = $1", *params)


async def record_step(run_id: UUID, seq: int, tool: str, kind: str, label: str, args: dict | None, result: dict | None, status: str) -> None:
    async with connection_or_direct() as conn:
        await conn.execute(
            """INSERT INTO huume_code_steps (run_id, seq, tool, kind, label, args, result, status)
               VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8)""",
            run_id, seq, tool, kind, label, json.dumps(args or {}), json.dumps(result or {}), status,
        )


async def list_tickets(project_id: UUID) -> list[dict]:
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT t.id, t.title, t.description, t.board_column, t.element_id,
                      (SELECT COUNT(*) FROM mw_subtasks s WHERE s.task_id = t.id) AS subtask_count
               FROM mw_tasks t WHERE t.project_id=$1
                 AND t.board_column IN ('todo','in_progress','changes_requested')
               ORDER BY t.created_at ASC""", project_id,
        )
    return [{**dict(row), "id": str(row["id"])} for row in rows]


async def read_ticket(project_id: UUID, task_id: UUID) -> dict | None:
    async with connection_or_direct() as conn:
        task = await conn.fetchrow(
            """SELECT id, title, description, board_column, element_id
               FROM mw_tasks WHERE id=$1 AND project_id=$2""", task_id, project_id,
        )
        if not task:
            return None
        subtasks = await conn.fetch(
            "SELECT title, is_done FROM mw_subtasks WHERE task_id=$1 ORDER BY position, created_at", task_id,
        )
    return {**dict(task), "id": str(task["id"]), "subtasks": [dict(row) for row in subtasks]}


def _task_event_payload(row) -> dict:
    payload = dict(row)
    for key in ("id", "project_id", "created_by", "assigned_to"):
        if payload.get(key) is not None:
            payload[key] = str(payload[key])
    for key in ("due_date", "completed_at", "created_at", "updated_at"):
        if payload.get(key) is not None:
            payload[key] = payload[key].isoformat()
    return payload


async def move_ticket_silently(project_id: UUID, task_id: UUID, column: str, actor_id: UUID) -> dict | None:
    """Move a bot-selected ticket without collaborator email fan-out.

    The normal project service is intentionally not called: it emails every
    collaborator on a column transition. We retain the board/history signal
    and the normal project-WS update so open boards converge without a reload.
    """
    async with connection_or_direct() as conn:
        previous = await conn.fetchrow(
            "SELECT board_column FROM mw_tasks WHERE id=$1 AND project_id=$2", task_id, project_id,
        )
        if previous is None or previous["board_column"] == column:
            return None
        row = await conn.fetchrow(
            """UPDATE mw_tasks
               SET board_column=$1, status='pending',
                   completed_at=CASE WHEN board_column='done' THEN NULL ELSE completed_at END,
                   updated_at=NOW()
               WHERE id=$2 AND project_id=$3
               RETURNING id, project_id, created_by, title, description, board_column,
                         priority, status, assigned_to, due_date, completed_at, created_at,
                         updated_at, progress_note, category, element_id, review_note""",
            column, task_id, project_id,
        )
        if row is None:
            return None
        await conn.execute(
            """INSERT INTO mw_task_history (task_id, task_id_text, project_id, actor_user_id, event_type, from_value, to_value, metadata)
               VALUES ($1,$2,$3,$4,'column_change',$5,$6,'{}'::jsonb)""",
            task_id, str(task_id), project_id, actor_id, previous["board_column"], column,
        )
    payload = _task_event_payload(row)
    payload["actor_id"] = str(actor_id)
    try:
        from app.matcha.services.matcha_work.task_events import broadcast_task_event
        await broadcast_task_event(project_id, "task.updated", payload)
    except Exception:
        logger.warning("Failed to broadcast Huume board move task=%s", task_id, exc_info=True)
    return payload


async def grounding(project_id: UUID, element_id: str | None) -> str:
    context, _manifest = await element_repo_service.build_grounding_context(element_id, project_id, char_budget=90_000)
    conventions = await element_repo_service.fetch_convention_docs(project_id, char_budget=15_000)
    return (conventions + "\n\n" + context)[:105_000]


async def repo_tree(repo: str, ref: str) -> list[dict]:
    if not _token():
        raise GitHubError("GITHUB_TOKEN is not set on the server.")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{GITHUB_API}/repos/{repo}/git/trees/{ref}", params={"recursive": "1"}, headers=_headers())
    if response.status_code >= 400:
        raise GitHubError(f"Unable to read repository tree ({response.status_code}).")
    return [item for item in response.json().get("tree", []) if item.get("type") == "blob"]


async def repo_file(repo: str, ref: str, path: str) -> str | None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{GITHUB_API}/repos/{repo}/contents/{path}", params={"ref": ref}, headers=_headers())
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise GitHubError(f"Unable to read {path} from GitHub ({response.status_code}).")
    data = response.json()
    if data.get("encoding") != "base64":
        return None
    return base64.b64decode(data.get("content") or "").decode("utf-8", errors="replace")


async def search_snapshot(project_id: UUID, query: str) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT path, LEFT(content, 1200) AS excerpt FROM mw_element_repo_files
               WHERE project_id=$1 AND (path ILIKE '%' || $2 || '%' OR content ILIKE '%' || $2 || '%')
               ORDER BY path LIMIT 30""", project_id, query,
        )
    return [dict(row) for row in rows]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
