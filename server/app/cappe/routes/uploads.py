"""Cappe shared image upload — product images, post covers, etc.

Reuses the platform storage service (S3/CloudFront-transparent). Scoped to an
owned site; images go under the `cappe` prefix.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeUploadResponse
from ._shared import get_owned_site

router = APIRouter()

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}

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
