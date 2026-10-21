"""Dropped videos: the upload straight to S3, the rows, and the stored files.

Phone clips are bigger than nginx lets through (20 MB), so the browser posts
the original directly to S3 with a presigned POST pinned to the exact size it
declared (`presign_upload`). `verify_upload` then checks what landed — size,
type and the container's first bytes — before ffmpeg ever reads it, and the
render (`render.py`, run by `workers/tasks/cappe_social_media.py`) fills in
the facts, the poster frames and the cuts.

Everything lives in the public bucket, like every other Cappe upload: the
renders must be (Meta fetches the video by URL), and the browser can post the
original there because that bucket's CORS already takes browser uploads (add
the Cappe dashboard's origin to it). Originals sit under unguessable keys,
are read by the renderer through a short presigned GET, and are removed with
the cuts when the row expires.

Files expire with the row (`expires_at`, 30 days): the sweep removes them
once no post is still waiting on them and no export still offers them for
download (`exports.py`). A post already published keeps its copy on the
network.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Optional
from uuid import UUID, uuid4

from app.core.services.storage import get_storage

from ..common import loads, loads_list

logger = logging.getLogger(__name__)

VIDEO_TYPES = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm"}
# Three minutes of phone video (what an export takes) runs 150–400 MB.
MAX_VIDEO_BYTES = 500 * 1024 * 1024
SOURCE_PREFIX = "cappe/social/sources"
RENDER_PREFIX = "cappe/social/renders"
FRAME_PREFIX = "cappe/social/frames"
PRESIGN_TTL_SECONDS = 900
# The renderer reads the original over HTTPS while it works.
SOURCE_READ_TTL_SECONDS = 3600
# A download link is handed to the browser and used at once.
DOWNLOAD_TTL_SECONDS = 600

COLUMNS = ("id, site_id, account_id, kind, status, filename, source_path, content_type, bytes, duration_ms, "
           "width, height, has_audio, trimmed, frames, renders, error, render_attempts, render_started_at, "
           "transcript, expires_at, created_at, updated_at")

# ISO-BMFF boxes an MP4/MOV may open with; QuickTime files from older
# cameras start with something other than `ftyp`.
_MOV_BOXES = {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot"}
_EBML = b"\x1a\x45\xdf\xa3"


class AssetStorageUnavailable(RuntimeError):
    """S3 + CloudFront aren't configured, so a video can't be taken."""


def _row(row) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    d = dict(row)
    d["frames"] = loads_list(d.get("frames")) or []
    d["renders"] = loads(d.get("renders")) or {}
    d["transcript"] = loads(d.get("transcript"))
    return d


def _storage():
    storage = get_storage()
    if not storage.s3_client or not storage.bucket or not storage.cloudfront_domain:
        raise AssetStorageUnavailable("Video uploads need S3 and CloudFront set up on this server.")
    return storage


def _split(path: str) -> tuple[str, str]:
    bucket, _, key = path[len("s3://"):].partition("/")
    return bucket, key


def _public_key(url: str, domain: str) -> Optional[str]:
    prefix = f"https://{domain}/"
    return url[len(prefix):] if url.startswith(prefix) else None


def public_key(url: Optional[str]) -> Optional[str]:
    """The public bucket's key for one of our CloudFront URLs."""
    domain = get_storage().cloudfront_domain
    return _public_key(url or "", domain) if domain else None


def looks_like_video(head: bytes, content_type: str) -> bool:
    """The first bytes match the container the browser said it was."""
    if content_type == "video/webm":
        return head.startswith(_EBML)
    return len(head) >= 8 and head[4:8] in _MOV_BOXES


def presign_upload(site_id: UUID, filename: str, content_type: str, size: int) -> dict[str, Any]:
    """A presigned POST for one original. Raises ValueError for a type or
    size we don't take, AssetStorageUnavailable without S3."""
    ext = VIDEO_TYPES.get(content_type)
    if ext is None:
        raise ValueError("Videos must be MP4, MOV or WebM")
    if size <= 0:
        raise ValueError("That file is empty")
    if size > MAX_VIDEO_BYTES:
        raise ValueError(f"Videos can be up to {MAX_VIDEO_BYTES // (1024 * 1024)} MB")
    storage = _storage()
    bucket = storage.bucket
    key = f"{SOURCE_PREFIX}/{site_id}/{uuid4().hex}{ext}"
    fields = {"Content-Type": content_type, "x-amz-server-side-encryption": "AES256"}
    conditions: list[Any] = [{name: value} for name, value in fields.items()]
    conditions.append(["content-length-range", size, size])
    post = storage.s3_client.generate_presigned_post(
        Bucket=bucket, Key=key, Fields=fields, Conditions=conditions, ExpiresIn=PRESIGN_TTL_SECONDS,
    )
    return {"upload_url": post["url"], "fields": post["fields"], "path": f"s3://{bucket}/{key}"}


def _verify_sync(path: str, size: int, content_type: str) -> Optional[str]:
    storage = _storage()
    bucket, key = _split(path)
    try:
        head = storage.s3_client.head_object(Bucket=bucket, Key=key)
    except Exception:  # noqa: BLE001 — botocore raises several shapes for "not there"
        return "The upload didn't finish. Try again."
    if int(head.get("ContentLength") or 0) != size or head.get("ContentType") != content_type:
        return "The upload doesn't match the file you picked. Try again."
    try:
        first = storage.s3_client.get_object(Bucket=bucket, Key=key, Range="bytes=0-15")["Body"].read()
    except Exception:  # noqa: BLE001
        return "The upload didn't finish. Try again."
    if not looks_like_video(first, content_type):
        return "That file isn't a video we can read. Try exporting it as an MP4."
    return None


async def verify_upload(asset: dict[str, Any]) -> Optional[str]:
    """Why the uploaded original can't be used, or None."""
    return await asyncio.to_thread(_verify_sync, asset["source_path"], int(asset["bytes"]), asset["content_type"])


def source_read_url(path: str) -> str:
    """A presigned GET the renderer hands to ffmpeg."""
    url = get_storage().get_presigned_download_url(path, expires_in=SOURCE_READ_TTL_SECONDS)
    if not url:
        raise AssetStorageUnavailable("Couldn't read the uploaded video.")
    return url


def download_url(key: str, *, filename: str, content_type: str, bucket: Optional[str] = None) -> str:
    """A short presigned GET that makes the browser save the file under
    `filename` (CloudFront URLs can't carry a Content-Disposition)."""
    storage = _storage()
    safe = filename.replace('"', "").replace("\\", "")
    return storage.s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket or storage.bucket, "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{safe}"', "ResponseContentType": content_type},
        ExpiresIn=DOWNLOAD_TTL_SECONDS,
    )


def source_location(asset: dict[str, Any]) -> tuple[str, str]:
    """(bucket, key) of the original."""
    return _split(asset["source_path"])


def _upload_path_sync(local_path: str, key: str, content_type: str) -> str:
    from boto3.s3.transfer import TransferConfig

    storage = _storage()
    storage.s3_client.upload_file(
        local_path, storage.bucket, key,
        ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256",
                   "CacheControl": "public, max-age=31536000, immutable"},
        # One thread: the worker is a single small slot.
        Config=TransferConfig(use_threads=False),
    )
    return f"https://{storage.cloudfront_domain}/{key}"


async def upload_render(local_path: str, asset_id: UUID, name: str) -> dict[str, Any]:
    """Upload a finished cut from disk; returns its public URL, key and size."""
    key = f"{RENDER_PREFIX}/{asset_id}/{name}-{uuid4().hex[:8]}.mp4"
    size = os.path.getsize(local_path)
    url = await asyncio.to_thread(_upload_path_sync, local_path, key, "video/mp4")
    return {"url": url, "key": key, "bytes": size}


async def upload_text(local_path: str, asset_id: UUID, name: str, ext: str, content_type: str) -> dict[str, Any]:
    """A small text file next to the cuts (the captions for YouTube)."""
    key = f"{RENDER_PREFIX}/{asset_id}/{name}-{uuid4().hex[:8]}{ext}"
    size = os.path.getsize(local_path)
    url = await asyncio.to_thread(_upload_path_sync, local_path, key, content_type)
    return {"url": url, "key": key, "bytes": size}


async def upload_frame(local_path: str, asset_id: UUID, index: int) -> str:
    key = f"{FRAME_PREFIX}/{asset_id}/{index}-{uuid4().hex[:8]}.jpg"
    return await asyncio.to_thread(_upload_path_sync, local_path, key, "image/jpeg")


def _delete_sync(asset: dict[str, Any]) -> None:
    storage = get_storage()
    if not storage.s3_client:
        return
    targets: list[tuple[str, str]] = []
    if asset.get("source_path", "").startswith("s3://"):
        targets.append(_split(asset["source_path"]))
    domain = storage.cloudfront_domain or ""
    for render in (asset.get("renders") or {}).values():
        key = _public_key(str((render or {}).get("url") or ""), domain) if domain else None
        if key:
            targets.append((storage.bucket, key))
    for bucket, key in targets:
        try:
            storage.s3_client.delete_object(Bucket=bucket, Key=key)
        except Exception:  # noqa: BLE001 — best effort; the lifecycle rule is the backstop
            logger.warning("cappe social: could not delete %s/%s", bucket, key)


async def delete_files(asset: dict[str, Any]) -> None:
    """Remove the original and the cuts. Poster frames stay: the queue still
    shows them for posts that went out."""
    await asyncio.to_thread(_delete_sync, asset)


# ── rows ────────────────────────────────────────────────────────────────────

_SAFE_NAME = re.compile(r"[^\w.\- ]+")


async def create(conn, *, site_id: UUID, account_id: UUID, filename: str, path: str,
                 content_type: str, size: int) -> dict[str, Any]:
    name = _SAFE_NAME.sub("", filename or "")[:200] or "video"
    row = await conn.fetchrow(
        f"""INSERT INTO cappe_social_assets (site_id, account_id, kind, status, filename, source_path, content_type, bytes)
            VALUES ($1, $2, 'video', 'uploading', $3, $4, $5, $6)
            RETURNING {COLUMNS}""",
        site_id, account_id, name, path, content_type, size,
    )
    return _row(row)


async def get(conn, site_id: UUID, asset_id: UUID) -> Optional[dict[str, Any]]:
    return _row(await conn.fetchrow(
        f"SELECT {COLUMNS} FROM cappe_social_assets WHERE id = $1 AND site_id = $2", asset_id, site_id,
    ))


async def get_by_id(conn, asset_id: UUID) -> Optional[dict[str, Any]]:
    return _row(await conn.fetchrow(f"SELECT {COLUMNS} FROM cappe_social_assets WHERE id = $1", asset_id))


async def load_many(conn, asset_ids: list[UUID]) -> dict[str, dict[str, Any]]:
    """Assets by id (as a string, the way post media names them)."""
    if not asset_ids:
        return {}
    rows = await conn.fetch(f"SELECT {COLUMNS} FROM cappe_social_assets WHERE id = ANY($1::uuid[])", list(asset_ids))
    return {str(r["id"]): _row(r) for r in rows}


async def mark_rendering(conn, asset_id: UUID) -> bool:
    row = await conn.fetchrow(
        "UPDATE cappe_social_assets SET status = 'rendering', error = NULL, updated_at = NOW() "
        "WHERE id = $1 AND status IN ('uploading', 'rendering') RETURNING id",
        asset_id,
    )
    return row is not None


async def start_render(conn, asset_id: UUID) -> None:
    await conn.execute(
        "UPDATE cappe_social_assets SET render_started_at = NOW(), render_attempts = render_attempts + 1, "
        "updated_at = NOW() WHERE id = $1",
        asset_id,
    )


async def record_facts(conn, asset_id: UUID, facts) -> None:
    await conn.execute(
        """UPDATE cappe_social_assets SET duration_ms = $2, width = $3, height = $4, has_audio = $5, trimmed = $6,
                  updated_at = NOW() WHERE id = $1""",
        asset_id, facts.duration_ms, facts.width, facts.height, facts.has_audio, facts.trimmed,
    )


async def record_frames(conn, asset_id: UUID, frames: list[dict[str, Any]]) -> None:
    await conn.execute(
        "UPDATE cappe_social_assets SET frames = $2::jsonb, updated_at = NOW() WHERE id = $1",
        asset_id, json.dumps(frames),
    )


async def record_transcript(conn, asset_id: UUID, transcript: dict[str, Any]) -> None:
    """The clip's timed words (`subtitles.compact`), or why there are none."""
    await conn.execute(
        "UPDATE cappe_social_assets SET transcript = $2::jsonb, updated_at = NOW() WHERE id = $1",
        asset_id, json.dumps(transcript),
    )


async def record_render(conn, asset_id: UUID, name: str, render: dict[str, Any]) -> None:
    await conn.execute(
        "UPDATE cappe_social_assets SET renders = renders || jsonb_build_object($2::text, $3::jsonb), "
        "updated_at = NOW() WHERE id = $1",
        asset_id, name, json.dumps(render),
    )


async def mark_ready(conn, asset_id: UUID) -> None:
    await conn.execute(
        "UPDATE cappe_social_assets SET status = 'ready', error = NULL, updated_at = NOW() "
        "WHERE id = $1 AND status = 'rendering'",
        asset_id,
    )


async def mark_failed(conn, asset_id: UUID, error: str) -> None:
    await conn.execute(
        "UPDATE cappe_social_assets SET status = 'failed', error = $2, updated_at = NOW() "
        "WHERE id = $1 AND status IN ('uploading', 'rendering')",
        asset_id, error[:500],
    )


async def delete(conn, site_id: UUID, asset_id: UUID) -> Optional[dict[str, Any]]:
    """Forget a video no post or export uses. Returns the row so the caller
    can remove the files once the connection is released."""
    return _row(await conn.fetchrow(
        """DELETE FROM cappe_social_assets a WHERE a.id = $1 AND a.site_id = $2
             AND NOT EXISTS (SELECT 1 FROM cappe_social_posts p
                             WHERE p.media @> jsonb_build_array(jsonb_build_object('asset_id', $3::text)))
             AND NOT EXISTS (SELECT 1 FROM cappe_social_exports e WHERE e.asset_id = a.id AND e.status <> 'deleted')
           RETURNING a.*""",
        asset_id, site_id, str(asset_id),
    ))


# ── the sweep's side ───────────────────────────────────────────────────────

# Posts that may still go out (or be retried) keep their video's files.
_LIVE_POSTS = ("draft", "scheduled", "rendering", "publishing", "partial", "failed")


async def stuck_renders(conn, *, minutes: int, limit: int) -> list[dict[str, Any]]:
    """Renders that never finished: the worker was restarted mid-cut, or the
    job never reached it."""
    rows = await conn.fetch(
        f"""SELECT {COLUMNS} FROM cappe_social_assets
            WHERE status = 'rendering' AND COALESCE(render_started_at, updated_at) < NOW() - make_interval(mins => $1)
            ORDER BY updated_at LIMIT $2""",
        minutes, limit,
    )
    return [_row(r) for r in rows]


async def touch_render(conn, asset_id: UUID) -> None:
    """Re-queued: start the stuck clock again so the next sweep waits."""
    await conn.execute(
        "UPDATE cappe_social_assets SET render_started_at = NOW(), updated_at = NOW() WHERE id = $1", asset_id,
    )


async def take_abandoned_uploads(conn, *, limit: int) -> list[dict[str, Any]]:
    """Uploads started a day ago and never completed: the rows go now, the
    caller removes whatever reached storage."""
    rows = await conn.fetch(
        """DELETE FROM cappe_social_assets WHERE id IN (
               SELECT id FROM cappe_social_assets WHERE status = 'uploading' AND created_at < NOW() - INTERVAL '1 day'
               ORDER BY created_at LIMIT $1)
           RETURNING *""",
        limit,
    )
    return [_row(r) for r in rows]


async def expired(conn, *, limit: int) -> list[dict[str, Any]]:
    """Videos past `expires_at` that no live post or export still needs."""
    rows = await conn.fetch(
        f"""SELECT {COLUMNS} FROM cappe_social_assets a
            WHERE a.expires_at < NOW() AND a.status <> 'deleted'
              AND NOT EXISTS (SELECT 1 FROM cappe_social_posts p
                              WHERE p.status = ANY($2::text[])
                                AND p.media @> jsonb_build_array(jsonb_build_object('asset_id', a.id::text)))
              AND NOT EXISTS (SELECT 1 FROM cappe_social_exports e
                              WHERE e.asset_id = a.id AND e.status <> 'deleted')
            ORDER BY a.expires_at LIMIT $1""",
        limit, list(_LIVE_POSTS),
    )
    return [_row(r) for r in rows]


async def mark_deleted(conn, asset_id: UUID) -> None:
    await conn.execute(
        "UPDATE cappe_social_assets SET status = 'deleted', renders = '{}'::jsonb, updated_at = NOW() WHERE id = $1",
        asset_id,
    )


def public_view(asset: dict[str, Any]) -> dict[str, Any]:
    """What the dashboard sees: no storage paths, renders as URL + size."""
    renders = {name: {k: r.get(k) for k in ("url", "width", "height", "duration_ms")}
               for name, r in (asset.get("renders") or {}).items() if isinstance(r, dict)}
    return {k: asset.get(k) for k in ("id", "kind", "status", "filename", "bytes", "duration_ms", "width", "height",
                                      "trimmed", "frames", "error", "created_at")} | {"renders": renders}


def poster(asset: Optional[dict[str, Any]]) -> Optional[str]:
    frames = (asset or {}).get("frames") or []
    middle = frames[len(frames) // 2] if frames else None
    return middle.get("url") if isinstance(middle, dict) else None


__all__ = [
    "VIDEO_TYPES", "MAX_VIDEO_BYTES", "AssetStorageUnavailable", "looks_like_video", "presign_upload",
    "verify_upload", "source_read_url", "public_key", "download_url", "source_location", "upload_render",
    "upload_text", "upload_frame", "delete_files",
    "create", "get", "get_by_id", "load_many", "mark_rendering", "start_render", "record_facts", "record_frames",
    "record_transcript", "record_render", "mark_ready", "mark_failed", "delete", "stuck_renders", "touch_render",
    "take_abandoned_uploads", "expired", "mark_deleted", "public_view", "poster",
]
