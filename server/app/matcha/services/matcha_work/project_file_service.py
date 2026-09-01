"""Project file attachment service.

Files attach to a project (task_id NULL) or to a specific kanban task
(task_id set). Project-scoped list paths must filter `task_id IS NULL`
so the Files tab doesn't surface task-scoped attachments.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile

from ....core.services.storage import get_storage
from ....database import get_connection

# The upload policy for project-scoped files (project root, element repos, and
# kanban-task attachments). Kept here — not in a route module — so every call
# site enforces one whitelist/limit/sink. Thread uploads and recruiting resume
# uploads deliberately use their OWN (different) whitelists and limits.
ALLOWED_PROJECT_FILE_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".csv", ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".heic", ".heif",
    ".pptx", ".md",
}

PROJECT_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


async def validate_and_store_project_upload(
    file: UploadFile,
    *,
    project_id: UUID,
    uploaded_by: UUID,
    prefix: str,
    task_id: Optional[UUID] = None,
    element_id: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> dict[str, Any]:
    """Validate an uploaded project file, push it to storage, and record it.

    One implementation of the project-file upload policy: extension whitelist →
    size limit → storage upload under `prefix` → `add_project_file` row. Raises
    HTTPException(400) on a rejected extension / oversize body / unparseable
    `folder_id`. `folder_id` is parsed AFTER the storage upload, preserving the
    original inline ordering at the project-files call site.
    """
    fname = file.filename or "file"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_PROJECT_FILE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    content = await file.read()
    if len(content) > PROJECT_FILE_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    storage_url = await get_storage().upload_file(
        content, fname,
        prefix=prefix,
        content_type=file.content_type,
    )

    folder_uuid: Optional[UUID] = None
    if folder_id:
        try:
            folder_uuid = UUID(folder_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid folder_id")

    return await add_project_file(
        project_id=project_id,
        uploaded_by=uploaded_by,
        filename=fname,
        storage_url=storage_url,
        content_type=file.content_type,
        file_size=len(content),
        task_id=task_id,
        element_id=element_id or None,
        folder_id=folder_uuid,
    )


async def list_project_files(project_id: UUID) -> list[dict[str, Any]]:
    """Root project files only — excludes task attachments AND element-scoped
    files (element_id IS NULL). Element repos surface via list_element_files."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, task_id, uploaded_by, filename, storage_url,
                      content_type, file_size, folder_id, element_id, created_at
               FROM mw_project_files
               WHERE project_id = $1 AND task_id IS NULL AND element_id IS NULL
               ORDER BY created_at DESC""",
            project_id,
        )
    return [dict(r) for r in rows]


async def list_element_files(project_id: UUID, element_id: str) -> list[dict[str, Any]]:
    """Files bucketed under one element (its context repo)."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, task_id, uploaded_by, filename, storage_url,
                      content_type, file_size, folder_id, element_id, created_at
               FROM mw_project_files
               WHERE project_id = $1 AND task_id IS NULL AND element_id = $2
               ORDER BY created_at DESC""",
            project_id, element_id,
        )
    return [dict(r) for r in rows]


async def list_task_files(project_id: UUID, task_id: UUID) -> list[dict[str, Any]]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT f.id, f.project_id, f.task_id, f.uploaded_by, f.filename,
                      f.storage_url, f.content_type, f.file_size, f.folder_id,
                      f.created_at,
                      -- Round this file was uploaded in: 1 + the number of
                      -- round_started boundaries that precede its upload time.
                      -- Lets the viewer keep the current round's files in the
                      -- foreground and archive earlier rounds' files. Derived
                      -- at read time — no round_index column on the table.
                      (1 + (SELECT COUNT(*) FROM mw_task_history h
                            WHERE h.task_id = f.task_id
                              AND h.event_type = 'round_started'
                              AND h.created_at <= f.created_at)) AS round_index,
                      COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name),
                               a.name, u.email)            AS uploader_name,
                      u.avatar_url                          AS uploader_avatar_url
               FROM mw_project_files f
               LEFT JOIN users u     ON u.id      = f.uploaded_by
               LEFT JOIN clients c   ON c.user_id = f.uploaded_by
               LEFT JOIN employees e ON e.user_id = f.uploaded_by
               LEFT JOIN admins a    ON a.user_id = f.uploaded_by
               WHERE f.project_id = $1 AND f.task_id = $2
               ORDER BY f.created_at DESC""",
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
            """SELECT f.id, f.project_id, f.task_id, f.uploaded_by, f.filename,
                      f.storage_url, f.content_type, f.file_size, f.folder_id,
                      f.created_at,
                      COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name),
                               a.name, u.email)            AS uploader_name,
                      u.avatar_url                          AS uploader_avatar_url
               FROM mw_project_files f
               LEFT JOIN users u     ON u.id      = f.uploaded_by
               LEFT JOIN clients c   ON c.user_id = f.uploaded_by
               LEFT JOIN employees e ON e.user_id = f.uploaded_by
               LEFT JOIN admins a    ON a.user_id = f.uploaded_by
               WHERE f.project_id = $1 AND f.task_id = ANY($2::uuid[])
               ORDER BY f.created_at DESC""",
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
    element_id: Optional[str] = None,
    folder_id: Optional[UUID] = None,
) -> dict[str, Any]:
    async with get_connection() as conn:
        # Drop a folder that isn't in this project OR whose element scope
        # doesn't match the file's — a file must not land in a root folder when
        # element-scoped, or in another element's folder.
        if folder_id is not None:
            folder = await conn.fetchrow(
                "SELECT element_id FROM mw_project_folders WHERE id = $1 AND project_id = $2",
                folder_id, project_id,
            )
            if folder is None or (folder["element_id"] or None) != (element_id or None):
                folder_id = None
        row = await conn.fetchrow(
            """INSERT INTO mw_project_files
               (project_id, task_id, uploaded_by, filename, storage_url, content_type,
                file_size, element_id, folder_id)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               RETURNING *""",
            project_id, task_id, uploaded_by, filename, storage_url, content_type,
            file_size, element_id, folder_id,
        )
        # Enrich with uploader name + avatar so the freshly-uploaded file
        # row matches list_task_files' shape — UI can render the uploader
        # pfp immediately without a follow-up refetch.
        uploader = await conn.fetchrow(
            """SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name),
                               a.name, u.email) AS uploader_name,
                      u.avatar_url             AS uploader_avatar_url
               FROM users u
               LEFT JOIN clients c   ON c.user_id = u.id
               LEFT JOIN employees e ON e.user_id = u.id
               LEFT JOIN admins a    ON a.user_id = u.id
               WHERE u.id = $1""",
            uploaded_by,
        )
    out = dict(row)
    if uploader:
        out["uploader_name"] = uploader["uploader_name"]
        out["uploader_avatar_url"] = uploader["uploader_avatar_url"]
    return out


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


def _bounded_channel_filename(
    attachment: dict[str, Any],
    url: str,
    *,
    infer_image_extension: bool,
) -> str:
    url_filename = url.rsplit("/", 1)[-1].split("?", 1)[0] if infer_image_extension else ""
    filename = str(attachment.get("filename") or url_filename or "attachment")
    if infer_image_extension and not os.path.splitext(filename)[1] and attachment.get("kind") == "image":
        content_extension = {
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/heic": ".heic",
            "image/heif": ".heif",
        }.get(attachment.get("content_type"), ".png")
        filename += content_extension
    if len(filename) <= 500:
        return filename
    stem, extension = os.path.splitext(filename)
    if extension and len(extension) < 500:
        return stem[:500 - len(extension)] + extension
    return filename[:500]


async def _sync_channel_attachments(
    conn,
    *,
    project_id: UUID,
    task_id: Optional[UUID],
    uploaded_by: UUID,
    attachments: list[dict[str, Any]],
    validate: bool,
) -> tuple[list[UUID], int]:
    """Shared channel-attachment insert path for project and task files."""
    ids: list[UUID] = []
    added = 0
    for att in attachments or []:
        if not isinstance(att, dict):
            continue
        url = att.get("url")
        if not isinstance(url, str) or not url:
            continue
        filename = _bounded_channel_filename(att, url, infer_image_extension=validate)
        try:
            file_size = int(att.get("size") or 0)
        except (TypeError, ValueError):
            continue
        if validate and (
            not url.startswith("https://")
            or not get_storage().is_supported_storage_path(url)
            or os.path.splitext(filename)[1].lower() not in ALLOWED_PROJECT_FILE_EXTENSIONS
            or file_size < 0
            or file_size > PROJECT_FILE_MAX_BYTES
        ):
            continue
        row = await conn.fetchrow(
            """INSERT INTO mw_project_files
                   (project_id, task_id, uploaded_by, filename, storage_url,
                    content_type, file_size)
               SELECT $1, $2::uuid, $3, $4, $5, $6, $7
               WHERE NOT EXISTS (
                   SELECT 1 FROM mw_project_files
                   WHERE project_id=$1
                     AND task_id IS NOT DISTINCT FROM $2::uuid
                     AND storage_url=$5
               )
               RETURNING id""",
            project_id,
            task_id,
            uploaded_by,
            filename,
            url,
            att.get("content_type"),
            file_size,
        )
        if row:
            ids.append(row["id"])
            added += 1
            continue
        if task_id is not None:
            existing = await conn.fetchval(
                """SELECT id FROM mw_project_files
                   WHERE project_id=$1 AND task_id=$2 AND storage_url=$3
                   LIMIT 1""",
                project_id,
                task_id,
                url,
            )
            if existing:
                ids.append(existing)
    return ids, added


async def sync_channel_attachments_to_project(
    conn,
    project_id: UUID,
    uploaded_by: UUID,
    attachments: list[dict[str, Any]],
) -> int:
    """Mirror chat attachments into root Files on the caller's transaction."""
    _, added = await _sync_channel_attachments(
        conn,
        project_id=project_id,
        task_id=None,
        uploaded_by=uploaded_by,
        attachments=attachments,
        validate=False,
    )
    return added


async def sync_channel_attachments_to_task(
    conn,
    project_id: UUID,
    task_id: UUID,
    uploaded_by: UUID,
    attachments: list[dict[str, Any]],
) -> list[UUID]:
    """Attach a decision-bound Espresso reply's files to its kanban ticket.

    Chat uploads already use permanent CloudFront URLs. Reusing that URL keeps
    screenshot replies fast and avoids copying blobs, while the project/task
    predicates prevent a crafted chat message from attaching across tickets.
    """
    owns_task = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM mw_tasks WHERE id=$1 AND project_id=$2)",
        task_id,
        project_id,
    )
    if not owns_task:
        return []
    ids, _ = await _sync_channel_attachments(
        conn,
        project_id=project_id,
        task_id=task_id,
        uploaded_by=uploaded_by,
        attachments=attachments,
        validate=True,
    )
    return ids


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
    """Root folders only (element_id IS NULL) — element folder trees surface
    via list_element_folders so they stay bucketed under their element."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, parent_id, name, element_id, created_by, created_at
               FROM mw_project_folders
               WHERE project_id = $1 AND element_id IS NULL
               ORDER BY name ASC""",
            project_id,
        )
    return [dict(r) for r in rows]


async def list_element_folders(project_id: UUID, element_id: str) -> list[dict[str, Any]]:
    """Folder tree scoped to one element."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, project_id, parent_id, name, element_id, created_by, created_at
               FROM mw_project_folders
               WHERE project_id = $1 AND element_id = $2
               ORDER BY name ASC""",
            project_id, element_id,
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
    element_id: Optional[str] = None,
) -> dict[str, Any]:
    async with get_connection() as conn:
        # Drop a parent that isn't in this project, or whose element scope
        # differs — an element's folder tree must stay within that element
        # (and a root folder must not nest under an element folder).
        if parent_id is not None:
            parent = await conn.fetchrow(
                "SELECT element_id FROM mw_project_folders WHERE id = $1 AND project_id = $2",
                parent_id, project_id,
            )
            if parent is None or (parent["element_id"] or None) != (element_id or None):
                parent_id = None
        row = await conn.fetchrow(
            """INSERT INTO mw_project_folders (project_id, parent_id, name, created_by, element_id)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING id, project_id, parent_id, name, element_id, created_by, created_at""",
            project_id, parent_id, (name.strip()[:200] or "Untitled"), created_by, element_id,
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
               RETURNING id, project_id, parent_id, name, element_id, created_by, created_at""",
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
                         content_type, file_size, folder_id, element_id, created_at""",
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
    reused, like `sync_channel_attachments_to_project`. NOTE: the copy lands
    at the project root (element_id NULL) — source is always a root file today.
    If copy is ever exposed from inside an element, propagate element_id here.
    Deduped on
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
                         content_type, file_size, folder_id, element_id, created_at""",
            project_id, src["uploaded_by"], src["filename"], src["storage_url"],
            src["content_type"], src["file_size"], folder_id,
        )
        if row is None:
            # Dedupe hit — return the pre-existing copy in this folder.
            row = await conn.fetchrow(
                """SELECT id, project_id, task_id, uploaded_by, filename, storage_url,
                          content_type, file_size, folder_id, element_id, created_at
                   FROM mw_project_files
                   WHERE project_id = $1 AND storage_url = $2 AND folder_id = $3
                   LIMIT 1""",
                project_id, src["storage_url"], folder_id,
            )
    return dict(row) if row else None
