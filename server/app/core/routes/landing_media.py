"""Landing page media — admin-uploadable hero/sizzle videos, logos, testimonials.

Stored as a single JSONB blob under the `landing_media` key in `platform_settings`.
"""

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..dependencies import require_admin
from ..models.auth import CurrentUser
from ...database import get_connection

logger = logging.getLogger(__name__)

public_router = APIRouter()
admin_router = APIRouter()


DEFAULT_LANDING_MEDIA: dict[str, Any] = {
    "hero_video_url": None,
    "hero_poster_url": None,
    "hero_headline": "Hiring, Perfected.",
    "hero_subcopy": "Today's leading teams trust Matcha to elevate recruiting, HR, and compliance.",
    "sizzle_videos": [],
    "customer_logos": [],
    "testimonials": [],
}

_ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".webm"}
_ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".svg", ".webp"}
_MAX_VIDEO_SIZE = 25 * 1024 * 1024  # 25 MB — plenty for a 20s product sizzle; keeps worker memory bounded
_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


async def _load_landing_media() -> dict[str, Any]:
    async with get_connection() as conn:
        raw = await conn.fetchval(
            "SELECT value FROM platform_settings WHERE key = 'landing_media'"
        )
    if raw is None:
        return dict(DEFAULT_LANDING_MEDIA)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid landing_media payload; returning defaults")
            return dict(DEFAULT_LANDING_MEDIA)
    else:
        parsed = raw
    if not isinstance(parsed, dict):
        return dict(DEFAULT_LANDING_MEDIA)
    merged = dict(DEFAULT_LANDING_MEDIA)
    merged.update(parsed)
    return merged


# ---------------------------------------------------------------------------
# Public (unauthenticated)
# ---------------------------------------------------------------------------


@public_router.get("/landing-media")
async def get_landing_media_public():
    """Public endpoint — returns the landing page media blob. No auth."""
    return await _load_landing_media()


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@admin_router.get("/landing-media")
async def get_landing_media_admin(
    current_user: CurrentUser = Depends(require_admin),
):
    return await _load_landing_media()


@admin_router.put("/landing-media")
async def update_landing_media(
    body: dict,
    current_user: CurrentUser = Depends(require_admin),
):
    """Replace the entire landing_media blob."""
    merged = dict(DEFAULT_LANDING_MEDIA)
    merged.update(body or {})
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('landing_media', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(merged),
        )
    return {"ok": True, "value": merged}


@admin_router.post("/landing-media/upload")
async def upload_landing_media(
    file: UploadFile = File(...),
    kind: str = Form("video"),  # "video" or "image"
    current_user: CurrentUser = Depends(require_admin),
):
    """Upload a hero/sizzle video or a logo/poster image. Returns CDN URL."""
    from ..services.storage import get_storage

    file_bytes = await file.read()
    filename = file.filename or "upload"
    ct = file.content_type or "application/octet-stream"
    ext = os.path.splitext(filename)[1].lower()

    if kind == "video":
        if ext not in _ALLOWED_VIDEO_EXT:
            raise HTTPException(status_code=400, detail=f"Video type not allowed: {ext}")
        if len(file_bytes) > _MAX_VIDEO_SIZE:
            raise HTTPException(status_code=400, detail="Video too large (max 25MB)")
    elif kind == "image":
        if ext not in _ALLOWED_IMAGE_EXT:
            raise HTTPException(status_code=400, detail=f"Image type not allowed: {ext}")
        if len(file_bytes) > _MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail="Image too large (max 5MB)")
    else:
        raise HTTPException(status_code=400, detail="kind must be 'video' or 'image'")

    storage = get_storage()
    url = await storage.upload_file(file_bytes, filename, prefix="landing", content_type=ct)
    return {"url": url, "filename": filename, "content_type": ct, "size": len(file_bytes)}
