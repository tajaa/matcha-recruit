"""Project file attachment service."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from ...database import get_connection


async def list_project_files(project_id: UUID) -> list[dict[str, Any]]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, uploaded_by, filename, storage_url,
                      content_type, file_size, created_at
               FROM mw_project_files
               WHERE project_id = $1
               ORDER BY created_at DESC""",
            project_id,
        )
    return [dict(r) for r in rows]


async def add_project_file(
    project_id: UUID,
    uploaded_by: UUID,
    filename: str,
    storage_url: str,
    content_type: Optional[str],
    file_size: int,
) -> dict[str, Any]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO mw_project_files
               (project_id, uploaded_by, filename, storage_url, content_type, file_size)
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING *""",
            project_id, uploaded_by, filename, storage_url, content_type, file_size,
        )
    return dict(row)


async def get_project_file(file_id: UUID, project_id: UUID) -> Optional[dict[str, Any]]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mw_project_files WHERE id = $1 AND project_id = $2",
            file_id, project_id,
        )
    return dict(row) if row else None


async def delete_project_file(file_id: UUID, project_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_project_files WHERE id = $1 AND project_id = $2",
            file_id, project_id,
        )
    return result.endswith("1")
