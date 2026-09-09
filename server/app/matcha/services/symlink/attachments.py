"""S3 staging for recipient uploads.

Same posture as `inbound_email._stage_intake_attachments`: validate name +
size, upload BEFORE the DB transaction opens, and discard on failure. Prefix
is `symlink/{company_id}/{symlink_id}` so a tenant's objects are enumerable.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.services.storage import get_storage
from app.matcha.services._shared.uploads import read_upload_capped

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_LINK = 8

# Server-derived MIME per allowed extension — never trust the client's
# content_type for storage (a .png sent as text/html is a stored XSS on any
# later inline render). Mirrors routes/ir_incidents/_shared.py.
_EXT_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".csv": "text/csv",
}


def validate_name(filename: Optional[str], accept: Optional[list[str]]) -> tuple[str, str, str]:
    name = (filename or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    if not name or len(name) > 200:
        raise HTTPException(status_code=400, detail="Invalid file name")
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    allowed = [a.lower() for a in (accept or list(_EXT_MIME))]
    if ext not in _EXT_MIME or ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(allowed)}")
    safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name)[:200]
    return safe, ext, _EXT_MIME[ext]


async def stage_upload(file: StarletteUploadFile, *, company_id, symlink_id, accept: Optional[list[str]]) -> dict:
    safe_name, _ext, mime = validate_name(file.filename, accept)
    content = await read_upload_capped(file, MAX_FILE_BYTES)
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    storage = get_storage()
    try:
        path = await storage.upload_private_file(
            content, safe_name, prefix=f"symlink/{company_id}/{symlink_id}", content_type=mime,
        )
    except Exception:
        logger.exception("[symlink] attachment upload failed for link %s", symlink_id)
        raise HTTPException(status_code=500, detail="Failed to upload attachment. Please try again.")
    return {"file_name": safe_name, "storage_path": path, "content_type": mime, "size_bytes": len(content)}


async def discard(storage_path: str) -> None:
    try:
        await get_storage().delete_private_file(storage_path)
    except Exception:
        logger.warning("[symlink] failed to discard staged object %s", storage_path)


async def insert_attachment(conn, *, symlink_id, company_id, slot: str, staged: dict):
    """Replace any live attachment in the same slot (one file per slot)."""
    old = await conn.fetch(
        """UPDATE symlink_attachments SET discarded_at = NOW()
            WHERE symlink_id = $1 AND slot = $2 AND discarded_at IS NULL
        RETURNING storage_path""",
        symlink_id, slot,
    )
    row = await conn.fetchrow(
        """INSERT INTO symlink_attachments
               (symlink_id, company_id, slot, storage_path, file_name, content_type, size_bytes)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, symlink_id, slot, storage_path, file_name, content_type, size_bytes, uploaded_at""",
        symlink_id, company_id, slot, staged["storage_path"], staged["file_name"],
        staged["content_type"], staged["size_bytes"],
    )
    return row, [r["storage_path"] for r in old]


async def read_bytes(storage_path: str) -> Optional[bytes]:
    """Fetch a private object's bytes (used by the credential apply path)."""
    try:
        return await get_storage().download_file(storage_path)
    except Exception:
        logger.exception("[symlink] failed to read %s", storage_path)
        return None


def presigned_url(storage_path: str) -> Optional[str]:
    return get_storage().get_presigned_download_url(storage_path, expires_in=600)


def serialize(row: Any) -> dict:
    return {
        "id": str(row["id"]),
        "slot": row["slot"],
        "file_name": row["file_name"],
        "content_type": row["content_type"],
        "size_bytes": int(row["size_bytes"] or 0),
        "uploaded_at": row["uploaded_at"].isoformat() if row["uploaded_at"] else None,
    }
