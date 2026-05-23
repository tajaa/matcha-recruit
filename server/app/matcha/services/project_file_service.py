"""Project file attachment service.

Files attach to a project (task_id NULL) or to a specific kanban task
(task_id set). Project-scoped list paths must filter `task_id IS NULL`
so the Files tab doesn't surface task-scoped attachments.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from ...database import get_connection


async def list_project_files(project_id: UUID) -> list[dict[str, Any]]:
    """Project-scoped files only (excludes task attachments)."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, task_id, uploaded_by, filename, storage_url,
                      content_type, file_size, folder_id, created_at
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
                      content_type, file_size, folder_id, created_at
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
                      content_type, file_size, folder_id, created_at
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


async def sync_channel_attachments_to_project(
    conn,
    project_id: UUID,
    uploaded_by: UUID,
    attachments: list[dict[str, Any]],
) -> int:
    """Mirror chat-message attachments into a project's root Files (task_id
    NULL). Best-effort and idempotent: deduped on (project_id, storage_url)
    among root files via NOT EXISTS, so message edits / WS redelivery don't
    double-insert. Runs on the caller's connection (same txn as the message
    insert). Must never raise into the send path — callers wrap in try/except.
    Returns the number of files added. Channel uploads return permanent
    CloudFront URLs, so the URL is stored directly (no S3 copy)."""
    added = 0
    for att in attachments or []:
        url = att.get("url")
        if not url:
            continue
        result = await conn.execute(
            """INSERT INTO mw_project_files
                   (project_id, task_id, uploaded_by, filename, storage_url, content_type, file_size)
               SELECT $1, NULL, $2, $3, $4, $5, $6
               WHERE NOT EXISTS (
                   SELECT 1 FROM mw_project_files
                   WHERE project_id = $1 AND storage_url = $4 AND task_id IS NULL
               )""",
            project_id,
            uploaded_by,
            (att.get("filename") or "attachment")[:500],
            url,
            att.get("content_type"),
            int(att.get("size") or 0),
        )
        if result.rsplit(" ", 1)[-1] == "1":
            added += 1
    return added


async def backfill_project_chat_files(project_id: UUID) -> int:
    """Mirror ALL existing attachments from the project's discussion-channel
    messages into root Files. Idempotent — deduped on (project_id, storage_url)
    among root files, so it's safe to call on every Media-tab open. Covers
    attachments posted before the per-message mirror existed (or that missed it
    due to a worker restart / race). Each attachment is credited to its message
    sender. Returns the number of new files added."""
    async with get_connection() as conn:
        channel_id = await conn.fetchval(
            "SELECT (project_data->>'discussion_channel_id')::uuid FROM mw_projects WHERE id = $1",
            project_id,
        )
        if not channel_id:
            return 0
        rows = await conn.fetch(
            """SELECT sender_id, attachments
               FROM channel_messages
               WHERE channel_id = $1 AND deleted_at IS NULL
                 AND attachments IS NOT NULL AND attachments::text NOT IN ('[]', 'null')""",
            channel_id,
        )
        added = 0
        for r in rows:
            raw = r["attachments"]
            try:
                atts = json.loads(raw) if isinstance(raw, str) else (raw or [])
            except (ValueError, TypeError):
                continue
            for att in atts or []:
                url = att.get("url") if isinstance(att, dict) else None
                if not url:
                    continue
                result = await conn.execute(
                    """INSERT INTO mw_project_files
                           (project_id, task_id, uploaded_by, filename, storage_url, content_type, file_size)
                       SELECT $1, NULL, $2, $3, $4, $5, $6
                       WHERE NOT EXISTS (
                           SELECT 1 FROM mw_project_files
                           WHERE project_id = $1 AND storage_url = $4 AND task_id IS NULL
                       )""",
                    project_id,
                    r["sender_id"],
                    (att.get("filename") or "attachment")[:500],
                    url,
                    att.get("content_type"),
                    int(att.get("size") or 0),
                )
                if result.rsplit(" ", 1)[-1] == "1":
                    added += 1
    return added


# ── Folders ──

async def list_project_folders(project_id: UUID) -> list[dict[str, Any]]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, parent_id, name, created_by, created_at
               FROM mw_project_folders
               WHERE project_id = $1
               ORDER BY name ASC""",
            project_id,
        )
    return [dict(r) for r in rows]


async def _folder_in_project(conn, folder_id: UUID, project_id: UUID) -> bool:
    """Guard against cross-project folder references — never trust a client id."""
    return bool(await conn.fetchval(
        "SELECT 1 FROM mw_project_folders WHERE id = $1 AND project_id = $2",
        folder_id, project_id,
    ))


async def create_project_folder(
    project_id: UUID,
    name: str,
    parent_id: Optional[UUID],
    created_by: UUID,
) -> dict[str, Any]:
    async with get_connection() as conn:
        # Drop a parent that isn't in this project rather than nest across tenants.
        if parent_id is not None and not await _folder_in_project(conn, parent_id, project_id):
            parent_id = None
        row = await conn.fetchrow(
            """INSERT INTO mw_project_folders (project_id, parent_id, name, created_by)
               VALUES ($1, $2, $3, $4)
               RETURNING id, project_id, parent_id, name, created_by, created_at""",
            project_id, parent_id, (name.strip()[:200] or "Untitled"), created_by,
        )
    return dict(row)


async def update_project_folder(
    folder_id: UUID,
    project_id: UUID,
    name: Optional[str] = None,
    parent_id: Optional[UUID] = None,
    clear_parent: bool = False,
) -> Optional[dict[str, Any]]:
    """Rename and/or reparent a folder. parent_id is set when given; pass
    clear_parent=True (with parent_id None) to move the folder to the root."""
    async with get_connection() as conn:
        # Reject a self-parent loop or a parent outside this project.
        if parent_id is not None and (
            parent_id == folder_id or not await _folder_in_project(conn, parent_id, project_id)
        ):
            parent_id = None
            clear_parent = False
        row = await conn.fetchrow(
            """UPDATE mw_project_folders
               SET name = COALESCE($3, name),
                   parent_id = CASE WHEN $5 THEN $4 ELSE COALESCE($4, parent_id) END
               WHERE id = $1 AND project_id = $2
               RETURNING id, project_id, parent_id, name, created_by, created_at""",
            folder_id, project_id,
            (name.strip()[:200] if name else None),
            parent_id, clear_parent,
        )
    return dict(row) if row else None


async def delete_project_folder(folder_id: UUID, project_id: UUID) -> bool:
    """Delete a folder. Its files fall back to the root (folder_id -> NULL via
    the FK ON DELETE SET NULL); child folders cascade-delete."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_project_folders WHERE id = $1 AND project_id = $2",
            folder_id, project_id,
        )
    return result.endswith("1")


async def move_file_to_folder(
    file_id: UUID,
    project_id: UUID,
    folder_id: Optional[UUID],
) -> Optional[dict[str, Any]]:
    """Move a file into a folder, or to the root when folder_id is None."""
    async with get_connection() as conn:
        # Don't let a file land in another project's folder.
        if folder_id is not None and not await _folder_in_project(conn, folder_id, project_id):
            return None
        row = await conn.fetchrow(
            """UPDATE mw_project_files
               SET folder_id = $3
               WHERE id = $1 AND project_id = $2
               RETURNING id, project_id, task_id, uploaded_by, filename, storage_url,
                         content_type, file_size, folder_id, created_at""",
            file_id, project_id, folder_id,
        )
    return dict(row) if row else None


async def copy_file_to_folder(
    file_id: UUID,
    project_id: UUID,
    folder_id: UUID,
) -> Optional[dict[str, Any]]:
    """Copy a project file into a folder, leaving the original in place.

    Used by the Media tab's "Add to Files": the source row stays at the root
    (so it remains in Media) and a new row is inserted pointing at the same
    storage URL under the target folder. No S3 copy — the CloudFront URL is
    reused, like `sync_channel_attachments_to_project`. Deduped on
    (project_id, storage_url, folder_id) so repeated adds don't pile up; the
    existing copy is returned in that case.
    """
    async with get_connection() as conn:
        # Never copy into another project's folder.
        if not await _folder_in_project(conn, folder_id, project_id):
            return None
        src = await conn.fetchrow(
            """SELECT uploaded_by, filename, storage_url, content_type, file_size
               FROM mw_project_files
               WHERE id = $1 AND project_id = $2 AND task_id IS NULL""",
            file_id, project_id,
        )
        if not src:
            return None
        row = await conn.fetchrow(
            """INSERT INTO mw_project_files
                   (project_id, task_id, uploaded_by, filename, storage_url,
                    content_type, file_size, folder_id)
               SELECT $1, NULL, $2, $3, $4, $5, $6, $7
               WHERE NOT EXISTS (
                   SELECT 1 FROM mw_project_files
                   WHERE project_id = $1 AND storage_url = $4 AND folder_id = $7
               )
               RETURNING id, project_id, task_id, uploaded_by, filename, storage_url,
                         content_type, file_size, folder_id, created_at""",
            project_id, src["uploaded_by"], src["filename"], src["storage_url"],
            src["content_type"], src["file_size"], folder_id,
        )
        if row is None:
            # Dedupe hit — return the pre-existing copy in this folder.
            row = await conn.fetchrow(
                """SELECT id, project_id, task_id, uploaded_by, filename, storage_url,
                          content_type, file_size, folder_id, created_at
                   FROM mw_project_files
                   WHERE project_id = $1 AND storage_url = $2 AND folder_id = $3
                   LIMIT 1""",
                project_id, src["storage_url"], folder_id,
            )
    return dict(row) if row else None
