"""Cappe shared image upload — product images, post covers, etc.

Reuses the platform storage service (S3/CloudFront-transparent). Scoped to an
owned site; images go under the `cappe` prefix.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ...core.services.image_gen import ImageGenError, generate_image
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeImageGenRequest, CappeUploadResponse
from ..services import image_quota
from ..services.design_gate import is_premium_plan
from ._shared import get_owned_site

router = APIRouter()

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# AI image generation — real per-image cost, so a DAILY per-account quota (not
# hourly). Free/hosting plans get a taste (upgrade funnel, like Merlin's lite
# tier); paid plans get headroom. Tunable; the Redis counter keys on account id.
# The quota itself lives in `services/image_quota.py` so Merlin's agent tool
# spends the SAME allowance as this button rather than a parallel one.
_IMG_GEN_DAILY_FREE = image_quota.DAILY_FREE
_IMG_GEN_DAILY_PAID = image_quota.DAILY_PAID
# NB: no image/svg+xml — SVGs can carry <script>/onload and are served from the
# tenant origin (*.gummfit.com / <sub>.hey-matcha.com) as product/cover images,
# so an uploaded SVG is a stored-XSS vector. Raster formats only.
_ALLOWED = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# Deliverables (digital products / service results) — larger, more types.
_MAX_DELIVERABLE_BYTES = 25 * 1024 * 1024  # 25 MB
_ALLOWED_DELIVERABLE = _ALLOWED | {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
}

# Hero background video — premium-only, short loops. Read fully into memory like
# the other uploads, so keep the cap modest (compressed hero loops are small).
_MAX_VIDEO_BYTES = 50 * 1024 * 1024  # 50 MB
_ALLOWED_VIDEO = {"video/mp4", "video/webm", "video/quicktime"}
_VIDEO_PLANS = {"pro", "business"}  # premium build tiers


@router.post("/sites/{site_id}/upload", response_model=CappeUploadResponse)
async def upload_image(
    site_id: UUID,
    file: UploadFile = File(...),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Upload an image for use on the site. Returns a public URL."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)

    if file.content_type not in _ALLOWED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image type")

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large (max 5 MB)")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    url = await get_storage().upload_file(
        file_bytes=data,
        filename=file.filename or "upload",
        prefix="cappe",
        content_type=file.content_type,
    )
    return CappeUploadResponse(url=url)


@router.post("/sites/{site_id}/generate-image", response_model=CappeUploadResponse)
async def generate_site_image(
    site_id: UUID,
    body: CappeImageGenRequest,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Generate an image with AI (Gemini) and return a public URL — used by the
    editor's ImageInput and by Merlin's generate_image op. A daily per-account
    quota guards real generation cost; the prompt is length-capped by the model.

    The quota counter increments on entry (before the model call), so a failed
    generation still counts — deliberate: each attempt costs an API call, and
    counting them is the cheap abuse guard until a real token wallet exists.
    """
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)

    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Describe the image you want")

    # Raises 429 (with Retry-After) if over the daily allowance. Shared with
    # Merlin's agent-loop generate_image tool — see services/image_quota.py.
    await image_quota.check_and_record(str(account.id), premium=is_premium_plan(account.plan))

    try:
        url = await generate_image(prompt, prefix="cappe/gen", aspect_ratio=body.aspect_ratio)
    except ImageGenError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't generate an image for that prompt — try rephrasing it.",
        )
    return CappeUploadResponse(url=url)


@router.post("/sites/{site_id}/upload-file", response_model=CappeUploadResponse)
async def upload_deliverable(
    site_id: UUID,
    file: UploadFile = File(...),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Upload a deliverable (digital product file / service result). Allows
    documents + archives up to 25 MB, scoped to an owned site."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)

    if file.content_type not in _ALLOWED_DELIVERABLE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    data = await file.read()
    if len(data) > _MAX_DELIVERABLE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large (max 25 MB)")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    url = await get_storage().upload_file(
        file_bytes=data,
        filename=file.filename or "deliverable",
        prefix="cappe",
        content_type=file.content_type,
    )
    return CappeUploadResponse(url=url)


@router.post("/sites/{site_id}/upload-video", response_model=CappeUploadResponse)
async def upload_video(
    site_id: UUID,
    file: UploadFile = File(...),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Upload a hero background video (premium plans only). Returns a public URL.

    Premium build tiers (Pro / Business) get the full-bleed autoplay hero video;
    free / hosting plans hit a 403 upsell. Mirrors the image upload otherwise.
    """
    if account.plan not in _VIDEO_PLANS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hero video is a premium feature. Upgrade to Pro to add a background video.",
        )

    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)

    if file.content_type not in _ALLOWED_VIDEO:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported video type (use MP4, WebM, or MOV)")

    data = await file.read()
    if len(data) > _MAX_VIDEO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Video too large (max 50 MB)")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    url = await get_storage().upload_file(
        file_bytes=data,
        filename=file.filename or "hero-video",
        prefix="cappe",
        content_type=file.content_type,
    )
    return CappeUploadResponse(url=url)
