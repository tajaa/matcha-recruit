"""Matcha Drive — company document store.

Folder tree per company in two spaces (`general`, `hr`), files in the private
bucket, per-user folder grants. Every public function takes an explicit
`actor` and checks capabilities through `drive_access`; `actor=None` is the
system path (HR case filing) and skips the check — routes always pass one.

Invariants:
  - Bytes go to the PRIVATE bucket only (`upload_private_file`); reads are
    short-lived presigned URLs. Nothing here returns `storage_path`.
  - Text extraction never fails an upload: it lands as text_status='failed'.
  - System folders (`system_key` set) cannot be renamed, moved or deleted —
    the HR cases flow files into them by key.
  - Moves never cross spaces: an HR document must not become company-wide by
    being dragged.
  - Search only ever queries folders the actor can READ, so an unreadable
    file is never returned, not even by name.
  - HR-space file reads/downloads/moves/deletes and every grant change write
    `drive_audit_log`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

import asyncpg

from .drive_access import (
    GRANT_PERMISSIONS,
    SPACES,
    DriveActor,
    DriveCap,
    DrivePermissionDenied,
    assert_cap,
    caps_list,
    effective_caps,
    folder_caps_map,
)

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_FILENAME_CHARS = 180
PRESIGN_SECONDS = 300

ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
_TEXT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}

# system_key -> (space, parent system_key, display name). Parents first.
SYSTEM_FOLDERS: dict[str, tuple[str, Optional[str], str]] = {
    "general_root": ("general", None, "Company"),
    "hr_root": ("hr", None, "HR"),
    "hr_templates": ("hr", "hr_root", "Templates"),
    "hr_discipline": ("hr", "hr_root", "Discipline"),
    "hr_discipline_drafts": ("hr", "hr_discipline", "Drafts"),
    "hr_discipline_signed": ("hr", "hr_discipline", "Signed"),
}
SPACE_ROOT_KEY = {"general": "general_root", "hr": "hr_root"}

_FOLDER_COLS = "id, company_id, parent_id, space, name, system_key, created_by, created_at, updated_at"
_FILE_COLS = (
    "f.id, f.company_id, f.folder_id, f.filename, f.content_type, f.file_size, "
    "f.text_status, f.source, f.linked_type, f.linked_id, f.uploaded_by, "
    "f.created_at, f.updated_at"
)


class DriveError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def _denied(exc: DrivePermissionDenied) -> DriveError:
    return DriveError(403, "You don't have access to do that in this folder.")


# ── Pure helpers ────────────────────────────────────────────────────────


_UNSAFE_CHARS = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]+')
_SPACES_RUN = re.compile(r"\s+")


def sanitize_filename(name: str) -> str:
    """Filesystem- and header-safe display name. Keeps the extension, strips
    path components/control chars, caps length. Empty input → 'file'."""
    raw = unicodedata.normalize("NFC", str(name or ""))
    raw = raw.replace("\\", "/").rsplit("/", 1)[-1]
    raw = _UNSAFE_CHARS.sub(" ", raw)
    raw = _SPACES_RUN.sub(" ", raw).strip()
    stem, ext = os.path.splitext(raw)
    if not ext and stem.startswith(".") and stem.count(".") == 1 and len(stem) > 1:
        stem, ext = "", stem  # ".pdf" is an extension with no stem, not a hidden file
    ext = ext.lower()[:10] if ext.strip(".") else ""
    stem = stem.strip(" .")[: MAX_FILENAME_CHARS - len(ext)].rstrip(" .") or "file"
    return f"{stem}{ext}"


def clean_folder_name(name: str) -> str:
    cleaned = _SPACES_RUN.sub(" ", _UNSAFE_CHARS.sub(" ", str(name or ""))).strip()
    if not cleaned or len(cleaned) > 200:
        raise DriveError(400, "Folder names must be 1–200 characters.")
    return cleaned


def file_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


@dataclass(frozen=True)
class PreparedFile:
    filename: str
    data: bytes
    content_type: str
    sha256: str
    extracted_text: Optional[str]
    text_status: str


def validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    """(sanitized filename, canonical content type) or DriveError. Pure."""
    safe = sanitize_filename(filename)
    ext = file_extension(safe)
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(e.lstrip(".") for e in ALLOWED_EXTENSIONS))
        raise DriveError(400, f"That file type isn't supported. Allowed: {allowed}.")
    if not data:
        raise DriveError(400, "That file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise DriveError(413, "Files can be at most 25 MB.")
    if ext == ".pdf" and not data[:1024].lstrip().startswith(b"%PDF"):
        raise DriveError(400, "That file isn't a valid PDF.")
    if ext == ".docx" and not data.startswith(b"PK"):
        raise DriveError(400, "That file isn't a valid Word document.")
    return safe, ALLOWED_EXTENSIONS[ext]


def _extract_text_sync(data: bytes, filename: str) -> tuple[Optional[str], str]:
    ext = file_extension(filename)
    if ext not in _TEXT_EXTENSIONS:
        return None, "unsupported"
    try:
        from app.matcha.services.er.er_document_parser import ERDocumentParser

        text, _pages = ERDocumentParser().extract_text_from_bytes(data, filename)
    except Exception:
        logger.warning("[drive] text extraction failed for %s", filename, exc_info=True)
        return None, "failed"
    text = (text or "").replace("\x00", "").strip()
    if not text:
        return None, "empty"
    return text[:MAX_TEXT_CHARS], "ok"


async def prepare_file(filename: str, data: bytes) -> PreparedFile:
    """Validate + hash + extract text. No DB, no storage — run it before
    taking a connection, extraction can take seconds on a large PDF."""
    safe, content_type = validate_upload(filename, data)
    text, status = await asyncio.to_thread(_extract_text_sync, data, safe)
    return PreparedFile(
        filename=safe,
        data=data,
        content_type=content_type,
        sha256=hashlib.sha256(data).hexdigest(),
        extracted_text=text,
        text_status=status,
    )


# ── Actor + folders ─────────────────────────────────────────────────────


async def load_actor(conn, *, user, company_id: UUID) -> DriveActor:
    from app.matcha.services.matcha_work.work_permissions import resolve_work_access

    access = await resolve_work_access(conn, user=user, company_id=company_id)
    return DriveActor(user_id=user.id, work_level=access.level)


async def ensure_system_folders(conn, company_id: UUID) -> dict[str, UUID]:
    """Idempotently seed the system folders; returns system_key -> folder id.

    On the run that first creates `hr_root`, every designated HR approver
    (`clients.is_hr_approver`) gets an explicit `edit` grant on it — a one-time
    seed of a visible, revocable grant, not an authorization rule.
    """
    rows = await conn.fetch(
        "SELECT system_key, id FROM drive_folders WHERE company_id = $1 AND system_key IS NOT NULL",
        company_id,
    )
    existing = {r["system_key"]: r["id"] for r in rows}
    if all(k in existing for k in SYSTEM_FOLDERS):
        return existing

    async with conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext('drive_seed:' || $1::text))", str(company_id),
        )
        rows = await conn.fetch(
            "SELECT system_key, id FROM drive_folders WHERE company_id = $1 AND system_key IS NOT NULL",
            company_id,
        )
        existing = {r["system_key"]: r["id"] for r in rows}
        created_hr_root = False
        for key, (space, parent_key, name) in SYSTEM_FOLDERS.items():
            if key in existing:
                continue
            parent_id = existing.get(parent_key) if parent_key else None
            # A user folder of the same name in the same spot is adopted
            # rather than duplicated (the sibling unique index forbids both).
            adopted = await conn.fetchval(
                """
                UPDATE drive_folders SET system_key = $4, updated_at = NOW()
                WHERE company_id = $1 AND space = $2
                  AND parent_id IS NOT DISTINCT FROM $3
                  AND lower(name) = lower($5) AND system_key IS NULL
                RETURNING id
                """,
                company_id, space, parent_id, key, name,
            )
            if adopted:
                existing[key] = adopted
                continue
            existing[key] = await conn.fetchval(
                """
                INSERT INTO drive_folders (company_id, parent_id, space, name, system_key)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                company_id, parent_id, space, name, key,
            )
            if key == "hr_root":
                created_hr_root = True

        if created_hr_root:
            await conn.execute(
                """
                INSERT INTO drive_folder_grants (company_id, folder_id, user_id, permission)
                SELECT $1, $2, c.user_id, 'edit'
                FROM clients c JOIN users u ON u.id = c.user_id
                WHERE c.company_id = $1 AND c.is_hr_approver AND u.is_active
                ON CONFLICT (folder_id, user_id) DO NOTHING
                """,
                company_id, existing["hr_root"],
            )
    return existing


async def _folder_with_caps(
    conn, *, company_id: UUID, folder_id: UUID, actor: Optional[DriveActor],
) -> tuple[dict[str, Any], frozenset[DriveCap]]:
    rows = await conn.fetch(
        """
        WITH RECURSIVE chain AS (
            SELECT id, parent_id, 0 AS depth FROM drive_folders
            WHERE id = $1 AND company_id = $2
            UNION ALL
            SELECT f.id, f.parent_id, c.depth + 1
            FROM drive_folders f JOIN chain c ON f.id = c.parent_id
            WHERE c.depth < 64
        )
        SELECT c.id, c.depth, g.permission
        FROM chain c
        LEFT JOIN drive_folder_grants g ON g.folder_id = c.id AND g.user_id = $3
        ORDER BY c.depth
        """,
        folder_id, company_id, actor.user_id if actor else None,
    )
    if not rows:
        raise DriveError(404, "That folder doesn't exist.")
    folder = await conn.fetchrow(
        f"SELECT {_FOLDER_COLS} FROM drive_folders WHERE id = $1", folder_id,
    )
    folder = dict(folder)
    if actor is None:
        return folder, frozenset(DriveCap)
    caps = effective_caps(actor, folder["space"], [r["permission"] for r in rows])
    return folder, caps


async def folder_caps(conn, *, company_id: UUID, folder_id: UUID, actor: Optional[DriveActor]):
    return await _folder_with_caps(conn, company_id=company_id, folder_id=folder_id, actor=actor)


async def _require(conn, *, company_id, folder_id, actor, cap: DriveCap) -> tuple[dict, frozenset]:
    folder, caps = await _folder_with_caps(conn, company_id=company_id, folder_id=folder_id, actor=actor)
    if not caps:
        # No capability at all reads as "doesn't exist", not "forbidden":
        # a folder name in the HR space is itself information.
        raise DriveError(404, "That folder doesn't exist.")
    try:
        assert_cap(caps, cap)
    except DrivePermissionDenied as exc:
        raise _denied(exc) from None
    return folder, caps


async def _load_space(conn, *, company_id: UUID, actor: DriveActor):
    folders = [dict(r) for r in await conn.fetch(
        f"SELECT {_FOLDER_COLS} FROM drive_folders WHERE company_id = $1 ORDER BY lower(name)",
        company_id,
    )]
    grants = {
        r["folder_id"]: r["permission"]
        for r in await conn.fetch(
            "SELECT folder_id, permission FROM drive_folder_grants WHERE company_id = $1 AND user_id = $2",
            company_id, actor.user_id,
        )
    }
    return folders, folder_caps_map(actor, folders, grants)


def _folder_out(folder: dict, caps: frozenset[DriveCap]) -> dict[str, Any]:
    return {
        "id": folder["id"],
        "parent_id": folder["parent_id"],
        "space": folder["space"],
        "name": folder["name"],
        "system_key": folder["system_key"],
        "is_system": folder["system_key"] is not None,
        "caps": caps_list(caps),
        "created_at": folder["created_at"],
    }


async def get_tree(conn, *, company_id: UUID, actor: DriveActor) -> dict[str, Any]:
    """Every folder the actor has any capability on, per space. A folder
    whose parent isn't visible is the client's root for that branch (an
    upload-only drop-box grant deep inside HR, for instance)."""
    system = await ensure_system_folders(conn, company_id)
    folders, caps = await _load_space(conn, company_id=company_id, actor=actor)
    spaces: dict[str, Any] = {}
    for space in SPACES:
        visible = [
            _folder_out(f, caps[f["id"]]) for f in folders
            if f["space"] == space and caps.get(f["id"])
        ]
        spaces[space] = {
            "visible": bool(visible),
            "root_folder_id": system[SPACE_ROOT_KEY[space]],
            "folders": visible,
        }
    return {"spaces": spaces}


async def _breadcrumbs(conn, folder_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        WITH RECURSIVE chain AS (
            SELECT id, parent_id, name, 0 AS depth FROM drive_folders WHERE id = $1
            UNION ALL
            SELECT f.id, f.parent_id, f.name, c.depth + 1
            FROM drive_folders f JOIN chain c ON f.id = c.parent_id WHERE c.depth < 64
        )
        SELECT id, name FROM chain ORDER BY depth DESC
        """,
        folder_id,
    )
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def _file_out(row) -> dict[str, Any]:
    return {k: row[k] for k in (
        "id", "folder_id", "filename", "content_type", "file_size", "text_status",
        "source", "linked_type", "linked_id", "uploaded_by", "created_at", "updated_at",
    )}


async def list_folder(conn, *, company_id: UUID, folder_id: UUID, actor: DriveActor) -> dict[str, Any]:
    folder, caps = await _folder_with_caps(conn, company_id=company_id, folder_id=folder_id, actor=actor)
    if not caps:
        raise DriveError(404, "That folder doesn't exist.")
    out: dict[str, Any] = {"folder": _folder_out(folder, caps), "breadcrumbs": [], "folders": [], "files": []}
    if DriveCap.LIST not in caps:
        # Drop-box: the actor may add here but sees nothing inside.
        return out
    out["breadcrumbs"] = await _breadcrumbs(conn, folder_id)
    children = await conn.fetch(
        f"SELECT {_FOLDER_COLS} FROM drive_folders WHERE parent_id = $1 ORDER BY lower(name)",
        folder_id,
    )
    # Caps only grow downward, so a child inherits at least the parent's set.
    child_grants = {
        r["folder_id"]: r["permission"]
        for r in await conn.fetch(
            "SELECT folder_id, permission FROM drive_folder_grants "
            "WHERE user_id = $1 AND folder_id = ANY($2::uuid[])",
            actor.user_id, [c["id"] for c in children],
        )
    } if children else {}
    out["folders"] = [
        _folder_out(dict(c), caps | effective_caps(actor, c["space"], [child_grants.get(c["id"])]))
        for c in children
    ]
    files = await conn.fetch(
        f"SELECT {_FILE_COLS} FROM drive_files f "
        "WHERE f.folder_id = $1 AND f.deleted_at IS NULL ORDER BY f.created_at DESC LIMIT 500",
        folder_id,
    )
    out["files"] = [_file_out(r) for r in files]
    return out


async def create_folder(
    conn, *, company_id: UUID, parent_id: UUID, name: str, actor: DriveActor,
) -> dict[str, Any]:
    parent, caps = await _require(conn, company_id=company_id, folder_id=parent_id, actor=actor, cap=DriveCap.MANAGE)
    cleaned = clean_folder_name(name)
    try:
        row = await conn.fetchrow(
            f"""
            INSERT INTO drive_folders (company_id, parent_id, space, name, created_by)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING {_FOLDER_COLS}
            """,
            company_id, parent_id, parent["space"], cleaned, actor.user_id,
        )
    except asyncpg.UniqueViolationError:
        raise DriveError(409, "A folder with that name already exists here.") from None
    if parent["space"] == "hr":
        await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id,
                          action="folder_create", folder_id=row["id"], details={"name": cleaned})
    return _folder_out(dict(row), caps)


async def _is_descendant(conn, *, ancestor_id: UUID, candidate_id: UUID) -> bool:
    return bool(await conn.fetchval(
        """
        WITH RECURSIVE chain AS (
            SELECT id, parent_id, 0 AS depth FROM drive_folders WHERE id = $1
            UNION ALL
            SELECT f.id, f.parent_id, c.depth + 1
            FROM drive_folders f JOIN chain c ON f.id = c.parent_id WHERE c.depth < 64
        )
        SELECT EXISTS (SELECT 1 FROM chain WHERE id = $2)
        """,
        candidate_id, ancestor_id,
    ))


async def update_folder(
    conn, *, company_id: UUID, folder_id: UUID, actor: DriveActor,
    name: Optional[str] = None, parent_id: Optional[UUID] = None,
) -> dict[str, Any]:
    folder, caps = await _require(conn, company_id=company_id, folder_id=folder_id, actor=actor, cap=DriveCap.MANAGE)
    if folder["system_key"]:
        raise DriveError(400, "System folders can't be renamed or moved.")
    new_name = clean_folder_name(name) if name is not None else folder["name"]
    new_parent = folder["parent_id"]
    if parent_id is not None and parent_id != folder["parent_id"]:
        target, _ = await _require(conn, company_id=company_id, folder_id=parent_id, actor=actor, cap=DriveCap.MANAGE)
        if target["space"] != folder["space"]:
            raise DriveError(400, "Folders can't move between the Company and HR spaces.")
        if await _is_descendant(conn, ancestor_id=folder_id, candidate_id=parent_id):
            raise DriveError(400, "A folder can't move inside itself.")
        new_parent = parent_id
    try:
        row = await conn.fetchrow(
            f"""
            UPDATE drive_folders SET name = $2, parent_id = $3, updated_at = NOW()
            WHERE id = $1 RETURNING {_FOLDER_COLS}
            """,
            folder_id, new_name, new_parent,
        )
    except asyncpg.UniqueViolationError:
        raise DriveError(409, "A folder with that name already exists there.") from None
    if folder["space"] == "hr":
        await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id,
                          action="folder_update", folder_id=folder_id,
                          details={"name": new_name, "parent_id": str(new_parent) if new_parent else None})
    return _folder_out(dict(row), caps)


async def delete_folder(conn, *, company_id: UUID, folder_id: UUID, actor: DriveActor) -> None:
    folder, _ = await _require(conn, company_id=company_id, folder_id=folder_id, actor=actor, cap=DriveCap.MANAGE)
    if folder["system_key"]:
        raise DriveError(400, "System folders can't be deleted.")
    busy = await conn.fetchval(
        """
        SELECT EXISTS (SELECT 1 FROM drive_folders WHERE parent_id = $1)
            OR EXISTS (SELECT 1 FROM drive_files WHERE folder_id = $1 AND deleted_at IS NULL)
        """,
        folder_id,
    )
    if busy:
        raise DriveError(409, "That folder isn't empty.")
    system = await ensure_system_folders(conn, company_id)
    async with conn.transaction():
        # Soft-deleted files keep their bytes for retention; re-home them on
        # the space root so the RESTRICT FK doesn't pin an "empty" folder.
        await conn.execute(
            "UPDATE drive_files SET folder_id = $2 WHERE folder_id = $1 AND deleted_at IS NOT NULL",
            folder_id, system[SPACE_ROOT_KEY[folder["space"]]],
        )
        await conn.execute("DELETE FROM drive_folders WHERE id = $1", folder_id)
        if folder["space"] == "hr":
            await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id,
                              action="folder_delete", folder_id=folder_id, details={"name": folder["name"]})


# ── Files ───────────────────────────────────────────────────────────────


async def store_file(
    conn,
    *,
    company_id: UUID,
    folder_id: UUID,
    prepared: PreparedFile,
    uploaded_by: Optional[UUID],
    actor: Optional[DriveActor],
    source: str = "upload",
    source_ref: Optional[str] = None,
    linked_type: Optional[str] = None,
    linked_id: Optional[UUID] = None,
    filename: Optional[str] = None,
) -> dict[str, Any]:
    """Store prepared bytes in `folder_id`. `actor=None` is the system path.
    `filename` overrides the prepared name (the HR flow names files itself)."""
    from app.core.services.storage import get_storage

    folder, _ = await _require(conn, company_id=company_id, folder_id=folder_id, actor=actor, cap=DriveCap.ADD)
    name = sanitize_filename(filename) if filename else prepared.filename
    try:
        storage_path = await get_storage().upload_private_file(
            prepared.data, name,
            prefix=f"drive/{company_id}/{folder['space']}",
            content_type=prepared.content_type,
        )
    except RuntimeError:
        raise DriveError(503, "File storage isn't configured.") from None
    try:
        row = await conn.fetchrow(
            f"""
            INSERT INTO drive_files AS f (
                company_id, folder_id, filename, storage_path, content_type, file_size,
                sha256, extracted_text, text_status, source, source_ref,
                linked_type, linked_id, uploaded_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING {_FILE_COLS}
            """,
            company_id, folder_id, name, storage_path, prepared.content_type, len(prepared.data),
            prepared.sha256, prepared.extracted_text, prepared.text_status, source, source_ref,
            linked_type, linked_id, uploaded_by,
        )
    except Exception:
        try:
            await get_storage().delete_private_file(storage_path)
        except Exception:
            logger.warning("[drive] orphaned private object %s", storage_path, exc_info=True)
        raise
    if folder["space"] == "hr":
        await write_audit(conn, company_id=company_id, actor_user_id=uploaded_by,
                          action="file_add", file_id=row["id"], folder_id=folder_id,
                          details={"filename": name, "source": source})
    return _file_out(row)


async def _file_with_caps(conn, *, company_id: UUID, file_id: UUID, actor: Optional[DriveActor]):
    row = await conn.fetchrow(
        f"SELECT {_FILE_COLS}, f.storage_path, d.space FROM drive_files f "
        "JOIN drive_folders d ON d.id = f.folder_id "
        "WHERE f.id = $1 AND f.company_id = $2 AND f.deleted_at IS NULL",
        file_id, company_id,
    )
    if not row:
        raise DriveError(404, "That file doesn't exist.")
    _, caps = await _folder_with_caps(conn, company_id=company_id, folder_id=row["folder_id"], actor=actor)
    if DriveCap.READ not in caps:
        raise DriveError(404, "That file doesn't exist.")
    return dict(row), caps


async def get_file(conn, *, company_id: UUID, file_id: UUID, actor: DriveActor) -> dict[str, Any]:
    row, caps = await _file_with_caps(conn, company_id=company_id, file_id=file_id, actor=actor)
    out = _file_out(row)
    out["space"] = row["space"]
    out["caps"] = caps_list(caps)
    out["breadcrumbs"] = await _breadcrumbs(conn, row["folder_id"])
    return out


async def read_file_text(
    conn, *, company_id: UUID, file_id: UUID, actor: Optional[DriveActor], max_chars: int = MAX_TEXT_CHARS,
) -> dict[str, Any]:
    row, _ = await _file_with_caps(conn, company_id=company_id, file_id=file_id, actor=actor)
    text = await conn.fetchval("SELECT extracted_text FROM drive_files WHERE id = $1", file_id)
    if row["space"] == "hr":
        await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id if actor else None,
                          action="file_read_text", file_id=file_id, folder_id=row["folder_id"])
    return {
        "id": row["id"], "filename": row["filename"], "text_status": row["text_status"],
        "text": (text or "")[:max_chars], "truncated": bool(text and len(text) > max_chars),
    }


async def read_file_bytes(conn, *, company_id: UUID, file_id: UUID, actor: Optional[DriveActor]) -> tuple[dict, bytes]:
    from app.core.services.storage import get_storage

    row, _ = await _file_with_caps(conn, company_id=company_id, file_id=file_id, actor=actor)
    data = await get_storage().download_file(row["storage_path"])
    if row["space"] == "hr":
        await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id if actor else None,
                          action="file_read", file_id=file_id, folder_id=row["folder_id"])
    return _file_out(row), data


async def presign_download(conn, *, company_id: UUID, file_id: UUID, actor: DriveActor) -> dict[str, Any]:
    from app.core.services.storage import get_storage

    row, _ = await _file_with_caps(conn, company_id=company_id, file_id=file_id, actor=actor)
    url = get_storage().get_presigned_download_url(row["storage_path"], expires_in=PRESIGN_SECONDS)
    if not url:
        raise DriveError(503, "That file can't be downloaded right now.")
    if row["space"] == "hr":
        await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id,
                          action="file_download", file_id=file_id, folder_id=row["folder_id"])
    return {"url": url, "filename": row["filename"], "expires_in": PRESIGN_SECONDS}


async def update_file(
    conn, *, company_id: UUID, file_id: UUID, actor: DriveActor,
    filename: Optional[str] = None, folder_id: Optional[UUID] = None,
) -> dict[str, Any]:
    row, caps = await _file_with_caps(conn, company_id=company_id, file_id=file_id, actor=actor)
    try:
        assert_cap(caps, DriveCap.MANAGE)
    except DrivePermissionDenied as exc:
        raise _denied(exc) from None
    new_name = row["filename"]
    if filename is not None:
        new_name = sanitize_filename(filename)
        if file_extension(new_name) != file_extension(row["filename"]):
            new_name = f"{os.path.splitext(new_name)[0]}{file_extension(row['filename'])}"
    new_folder = row["folder_id"]
    if folder_id is not None and folder_id != row["folder_id"]:
        target, _ = await _require(conn, company_id=company_id, folder_id=folder_id, actor=actor, cap=DriveCap.ADD)
        if target["space"] != row["space"]:
            raise DriveError(400, "Files can't move between the Company and HR spaces.")
        new_folder = folder_id
    updated = await conn.fetchrow(
        f"UPDATE drive_files AS f SET filename = $2, folder_id = $3, updated_at = NOW() "
        f"WHERE f.id = $1 RETURNING {_FILE_COLS}",
        file_id, new_name, new_folder,
    )
    if row["space"] == "hr":
        await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id,
                          action="file_update", file_id=file_id, folder_id=new_folder,
                          details={"filename": new_name, "from_folder_id": str(row["folder_id"])})
    return _file_out(updated)


async def soft_delete_file(conn, *, company_id: UUID, file_id: UUID, actor: DriveActor) -> None:
    row, caps = await _file_with_caps(conn, company_id=company_id, file_id=file_id, actor=actor)
    try:
        assert_cap(caps, DriveCap.MANAGE)
    except DrivePermissionDenied as exc:
        raise _denied(exc) from None
    await conn.execute("UPDATE drive_files SET deleted_at = NOW(), updated_at = NOW() WHERE id = $1", file_id)
    if row["space"] == "hr":
        await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id,
                          action="file_delete", file_id=file_id, folder_id=row["folder_id"],
                          details={"filename": row["filename"]})


def _like_escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def search(
    conn, *, company_id: UUID, q: str, actor: DriveActor,
    space: Optional[str] = None, limit: int = 25,
) -> list[dict[str, Any]]:
    q = (q or "").strip()[:200]
    if len(q) < 2:
        return []
    if space is not None and space not in SPACES:
        raise DriveError(400, "Unknown space.")
    limit = min(max(int(limit or 25), 1), 50)
    folders, caps = await _load_space(conn, company_id=company_id, actor=actor)
    readable = [
        f["id"] for f in folders
        if DriveCap.READ in caps.get(f["id"], frozenset()) and (space is None or f["space"] == space)
    ]
    if not readable:
        return []
    names = {f["id"]: f for f in folders}
    rows = await conn.fetch(
        f"""
        SELECT {_FILE_COLS}
        FROM drive_files f
        WHERE f.company_id = $1 AND f.deleted_at IS NULL
          AND f.folder_id = ANY($2::uuid[])
          AND (
            to_tsvector('english', f.filename || ' ' || COALESCE(f.extracted_text, ''))
                @@ plainto_tsquery('english', $3)
            OR f.filename ILIKE '%' || $4 || '%' ESCAPE '\\'
          )
        ORDER BY ts_rank(
            to_tsvector('english', f.filename || ' ' || COALESCE(f.extracted_text, '')),
            plainto_tsquery('english', $3)
        ) DESC, f.created_at DESC
        LIMIT $5
        """,
        company_id, readable, q, _like_escape(q), limit,
    )
    out = []
    for r in rows:
        item = _file_out(r)
        folder = names.get(r["folder_id"])
        item["folder_name"] = folder["name"] if folder else None
        item["space"] = folder["space"] if folder else None
        out.append(item)
    return out


# ── Grants ──────────────────────────────────────────────────────────────


async def list_grants(conn, *, company_id: UUID, folder_id: UUID, actor: DriveActor) -> list[dict[str, Any]]:
    await _require(conn, company_id=company_id, folder_id=folder_id, actor=actor, cap=DriveCap.GRANT)
    rows = await conn.fetch(
        """
        SELECT g.user_id, g.permission, g.created_at, u.email,
               COALESCE(c.name, NULLIF(TRIM(COALESCE(e.first_name, '') || ' ' || COALESCE(e.last_name, '')), ''), u.email) AS name
        FROM drive_folder_grants g
        JOIN users u ON u.id = g.user_id
        LEFT JOIN clients c ON c.user_id = g.user_id AND c.company_id = g.company_id
        LEFT JOIN employees e ON e.user_id = g.user_id AND e.org_id = g.company_id
        WHERE g.folder_id = $1 AND g.company_id = $2
        ORDER BY lower(u.email)
        """,
        folder_id, company_id,
    )
    return [dict(r) for r in rows]


async def set_grant(
    conn, *, company_id: UUID, folder_id: UUID, user_id: UUID, permission: str, actor: DriveActor,
) -> dict[str, Any]:
    if permission not in GRANT_PERMISSIONS:
        raise DriveError(400, "Permission must be view, upload, or edit.")
    await _require(conn, company_id=company_id, folder_id=folder_id, actor=actor, cap=DriveCap.GRANT)
    member = await conn.fetchval(
        """
        SELECT EXISTS (SELECT 1 FROM clients WHERE user_id = $1 AND company_id = $2)
            OR EXISTS (SELECT 1 FROM employees WHERE user_id = $1 AND org_id = $2 AND termination_date IS NULL)
        """,
        user_id, company_id,
    )
    if not member:
        raise DriveError(400, "That person isn't a member of this company.")
    await conn.execute(
        """
        INSERT INTO drive_folder_grants (company_id, folder_id, user_id, permission, granted_by)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (folder_id, user_id)
        DO UPDATE SET permission = EXCLUDED.permission, granted_by = EXCLUDED.granted_by
        """,
        company_id, folder_id, user_id, permission, actor.user_id,
    )
    await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id, action="grant_set",
                      folder_id=folder_id, details={"user_id": str(user_id), "permission": permission})
    return {"user_id": user_id, "permission": permission}


async def remove_grant(conn, *, company_id: UUID, folder_id: UUID, user_id: UUID, actor: DriveActor) -> None:
    await _require(conn, company_id=company_id, folder_id=folder_id, actor=actor, cap=DriveCap.GRANT)
    await conn.execute(
        "DELETE FROM drive_folder_grants WHERE folder_id = $1 AND user_id = $2 AND company_id = $3",
        folder_id, user_id, company_id,
    )
    await write_audit(conn, company_id=company_id, actor_user_id=actor.user_id, action="grant_remove",
                      folder_id=folder_id, details={"user_id": str(user_id)})


# ── Audit ───────────────────────────────────────────────────────────────


async def write_audit(
    conn, *, company_id: UUID, actor_user_id: Optional[UUID], action: str,
    file_id: Optional[UUID] = None, folder_id: Optional[UUID] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO drive_audit_log (company_id, file_id, folder_id, actor_user_id, action, details)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        company_id, file_id, folder_id, actor_user_id, action, json.dumps(details or {}),
    )
