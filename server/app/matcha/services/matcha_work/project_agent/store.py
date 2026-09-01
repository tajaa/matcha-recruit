"""Worker-safe persistence and repository reads for project agents."""
from __future__ import annotations

import base64
import json
from typing import Any
from uuid import UUID

import httpx

from app.database import connection_or_direct
from app.matcha.services.matcha_work.github_service import GITHUB_API, GitHubError, _headers, _token

from .guards import is_sensitive_read_path, numbered_line_window


async def mark_run(run_id: UUID, *, status: str, **values: Any) -> None:
    assignments = [
        "status = $2",
        "completed_at = CASE WHEN $2 IN ('done', 'failed') THEN NOW() ELSE completed_at END",
    ]
    params: list[Any] = [run_id, status]
    json_columns = {"result", "token_usage"}
    for column in ("result", "error", "model_calls", "files_read", "token_usage"):
        if column not in values:
            continue
        assignments.append(
            f"{column} = ${len(params) + 1}" + ("::jsonb" if column in json_columns else "")
        )
        value = json.dumps(values[column]) if column in json_columns else values[column]
        params.append(value)
    async with connection_or_direct() as conn:
        await conn.execute(
            f"UPDATE mw_project_agent_runs SET {', '.join(assignments)} WHERE id = $1",
            *params,
        )


async def record_step(
    run_id: UUID,
    seq: int,
    tool: str,
    kind: str,
    label: str,
    args: dict | None,
    result: dict | None,
    status: str,
) -> None:
    async with connection_or_direct() as conn:
        await conn.execute(
            """INSERT INTO mw_project_agent_steps
               (run_id, seq, tool, kind, label, args, result, status)
               VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8)""",
            run_id,
            seq,
            tool,
            kind,
            label,
            json.dumps(args or {}),
            json.dumps(result or {}),
            status,
        )


async def search_snapshot(project_id: UUID, query: str) -> list[dict]:
    term = (query or "").strip()
    if not term:
        return []
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT path, LEFT(content, 1600) AS excerpt
               FROM mw_element_repo_files
               WHERE project_id=$1
                 AND (path ILIKE '%' || $2 || '%' OR content ILIKE '%' || $2 || '%')
               ORDER BY path LIMIT 24""",
            project_id,
            term,
        )
    return [dict(row) for row in rows if not is_sensitive_read_path(row["path"])]


async def repo_tree(repo: str, ref: str) -> list[dict]:
    if not _token():
        raise GitHubError("GITHUB_TOKEN is not set on the server.")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GITHUB_API}/repos/{repo}/git/trees/{ref}",
            params={"recursive": "1"},
            headers=_headers(),
        )
    if response.status_code >= 400:
        raise GitHubError(f"Unable to read repository tree ({response.status_code}).")
    return [
        item for item in response.json().get("tree", [])
        if item.get("type") == "blob" and not is_sensitive_read_path(item.get("path", ""))
    ]


async def read_repo_file(
    repo: str,
    ref: str,
    path: str,
    *,
    start_line: int = 1,
    end_line: int | None = None,
) -> dict:
    if not _token():
        raise GitHubError("GITHUB_TOKEN is not set on the server.")
    normalized = (path or "").strip().lstrip("/")
    if is_sensitive_read_path(normalized):
        raise ValueError(f"Refusing sensitive repository path: {normalized}")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GITHUB_API}/repos/{repo}/contents/{normalized}",
            params={"ref": ref},
            headers=_headers(),
        )
    if response.status_code == 404:
        raise FileNotFoundError(f"File not found: {normalized}")
    if response.status_code >= 400:
        raise GitHubError(f"Unable to read {normalized} from GitHub ({response.status_code}).")
    data = response.json()
    if data.get("type") != "file" or data.get("encoding") != "base64":
        raise ValueError(f"Unsupported repository object: {normalized}")
    content = base64.b64decode(data.get("content") or "").decode("utf-8", errors="replace")
    return {
        "path": normalized,
        **numbered_line_window(content, start_line=start_line, end_line=end_line),
    }


async def load_task_draft_context(project_id: UUID) -> dict:
    """Load compact project metadata through the worker-safe connection path."""
    async with connection_or_direct() as conn:
        collaborator_rows = await conn.fetch(
            """SELECT pc.user_id,
                      COALESCE(c.name,
                               NULLIF(BTRIM(CONCAT(e.first_name, ' ', e.last_name)), ''),
                               a.name, u.email) AS name
               FROM mw_project_collaborators pc
               JOIN users u ON u.id=pc.user_id
               LEFT JOIN admins a ON a.user_id=pc.user_id
               LEFT JOIN clients c ON c.user_id=pc.user_id
               LEFT JOIN employees e ON e.user_id=pc.user_id
               WHERE pc.project_id=$1 AND pc.status='active'
               ORDER BY pc.created_at ASC""",
            project_id,
        )
        element_rows = await conn.fetch(
            """SELECT id, name, description FROM mw_project_elements
               WHERE project_id=$1 AND kind IS DISTINCT FROM '_repository_snapshot'
               ORDER BY \"order\" ASC, created_at ASC""",
            project_id,
        )
        note_rows = await conn.fetch(
            """SELECT element_id, kind, body, url FROM mw_element_notes
               WHERE project_id=$1 ORDER BY created_at DESC""",
            project_id,
        )
        done_rows = await conn.fetch(
            """SELECT title FROM mw_tasks
               WHERE project_id=$1 AND status='completed'
                 AND completed_at >= NOW() - INTERVAL '7 days'
               ORDER BY completed_at DESC LIMIT 15""",
            project_id,
        )

    notes_by_element: dict[str, list[str]] = {}
    for row in note_rows:
        text = (row["url"] if row["kind"] == "link" else row["body"]) or ""
        if str(text).strip():
            notes_by_element.setdefault(str(row["element_id"]), []).append(str(text).strip())

    return {
        "collaborators": [
            {"user_id": str(row["user_id"]), "name": row["name"]}
            for row in collaborator_rows if row["name"]
        ],
        "elements": [
            {
                "id": str(row["id"]),
                "name": row["name"],
                "description": row["description"],
                "notes": notes_by_element.get(str(row["id"]), [])[:5],
            }
            for row in element_rows if row["name"]
        ],
        "recent_done": [row["title"] for row in done_rows if row["title"]],
    }
