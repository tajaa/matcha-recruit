"""Project file attachment service.

Files attach to a project (task_id NULL) or to a specific kanban task
(task_id set). Project-scoped list paths must filter `task_id IS NULL`
so the Files tab doesn't surface task-scoped attachments.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from ...database import get_connection


async def list_project_files(project_id: UUID) -> list[dict[str, Any]]:
    """Project-scoped files only (excludes task attachments)."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, task_id, uploaded_by, filename, storage_url,
                      content_type, file_size, created_at
               FROM mw_project_files
               WHERE project_id = $1 AND task_id IS NULL
               ORDER BY created_at DESC""",
            project_id,
        )
    return [dict(r) for r in rows]


async def list_task_files(project_id: UUID, task_id: UUID) -> list[dict[str, Any]]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, task_id, uploaded_by, filename, storage_url,
                      content_type, file_size, created_at
               FROM mw_project_files
               WHERE project_id = $1 AND task_id = $2
               ORDER BY created_at DESC""",
            project_id, task_id,
        )
    return [dict(r) for r in rows]


async def list_files_for_tasks(project_id: UUID, task_ids: list[UUID]) -> dict[str, list[dict[str, Any]]]:
    """Bulk fetch keyed by task_id string. Used to embed attachments in the
    kanban GET so cards can render thumbnails without N+1."""
    if not task_ids:
        return {}
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, task_id, uploaded_by, filename, storage_url,
                      content_type, file_size, created_at
               FROM mw_project_files
               WHERE project_id = $1 AND task_id = ANY($2::uuid[])
               ORDER BY created_at DESC""",
            project_id, task_ids,
        )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        d = dict(r)
        key = str(d["task_id"])
        grouped.setdefault(key, []).append(d)
    return grouped


async def add_project_file(
    project_id: UUID,
    uploaded_by: UUID,
    filename: str,
    storage_url: str,
    content_type: Optional[str],
    file_size: int,
    task_id: Optional[UUID] = None,
) -> dict[str, Any]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO mw_project_files
               (project_id, task_id, uploaded_by, filename, storage_url, content_type, file_size)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING *""",
            project_id, task_id, uploaded_by, filename, storage_url, content_type, file_size,
        )
    return dict(row)


async def get_project_file(file_id: UUID, project_id: UUID) -> Optional[dict[str, Any]]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mw_project_files WHERE id = $1 AND project_id = $2",
            file_id, project_id,
        )
    return dict(row) if row else None


async def get_task_file(file_id: UUID, project_id: UUID, task_id: UUID) -> Optional[dict[str, Any]]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mw_project_files WHERE id = $1 AND project_id = $2 AND task_id = $3",
            file_id, project_id, task_id,
        )
    return dict(row) if row else None


async def delete_project_file(file_id: UUID, project_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_project_files WHERE id = $1 AND project_id = $2",
            file_id, project_id,
        )
    return result.endswith("1")
