"""Cappe shared image upload — product images, post covers, etc. — and the
site's image library.

Reuses the platform storage service (S3/CloudFront-transparent). Scoped to an
owned site; images go under the `cappe` prefix. Every image is re-encoded
before it is stored (`services/media.py`), so a photo's EXIF — GPS position
included — never reaches the public CDN.
"""
import asyncio
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from ...core.services.image_gen import ImageGenError, generate_image
from ...core.services.redis_cache import check_rate_limit
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeAsset,
    CappeAssetList,
    CappeAssetPatch,
    CappeImageGenRequest,
    CappeUploadResponse,
)
from ..services import cappe_assets, image_quota, media, upload_guard
from ..services.design_gate import is_premium_plan
from ..services.image_prompting import build_image_prompt
from ..services.merlin.catalog import AI_IMAGE_SIZES, DEFAULT_AI_IMAGE_SIZE
from ._shared import get_owned_site, read_capped

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
# The library takes a phone photo as it comes off the camera; it is re-encoded
# and capped at media.MAX_SIDE before anything is stored.
_MAX_LIBRARY_BYTES = 15 * 1024 * 1024

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

# Deliverables (digital products / service results) — larger, more types.
_MAX_DELIVERABLE_BYTES = 25 * 1024 * 1024  # 25 MB

# Hero background video — premium-only, short loops. Read fully into memory like
# the other uploads, so keep the cap modest (compressed hero loops are small).
_MAX_VIDEO_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/sites/{site_id}/upload", response_model=CappeUploadResponse)
async def upload_image(
    site_id: UUID,
    file: UploadFile = File(...),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Upload an image for use on the site. Returns a public URL."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)

    if file.content_type not in upload_guard.ALLOWED_IMAGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image type")

    data = await read_capped(file, _MAX_BYTES, "Image too large (max 5 MB)")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    content_type = upload_guard.verify_upload(data, file.content_type, upload_guard.ALLOWED_IMAGE)
    image = await _process(data, content_type, derivatives=False)
    url = await get_storage().upload_file(
        file_bytes=image.data,
        filename=media.filename_for(file.filename, image.ext),
        prefix="cappe",
        content_type=image.mime,
    )
    try:
        async with get_connection() as conn:
            await cappe_assets.record(
                conn, account_id=account.id, site_id=site["id"], kind="upload", url=url,
                width=image.width, height=image.height, size_bytes=len(image.data), mime=image.mime,
            )
    except Exception as exc:  # noqa: BLE001 — catalog bookkeeping never fails the upload
        logger.warning("cappe asset catalog insert failed (upload): %s", exc)
    return CappeUploadResponse(url=url)


async def _process(data: bytes, content_type: str, *, derivatives: bool) -> media.ProcessedImage:
    try:
        return await asyncio.to_thread(media.process_image, data, content_type, derivatives=derivatives)
    except media.ImageRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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
        site = await get_owned_site(conn, site_id, account.id)

    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Describe the image you want")

    # Raises 429 (with Retry-After) if over the daily allowance. Shared with
    # Merlin's agent-loop generate_image tool — see services/image_quota.py.
    await image_quota.check_and_record(str(account.id), premium=is_premium_plan(account.plan))

    # Default to 2K, not the model's own 1K default — section backgrounds
    # render at `background-size: cover` full-bleed (render.py), and 1K reads
    # soft once stretched across one. An explicit request wins if valid.
    size = body.image_size.strip().upper() if body.image_size else None
    if size not in AI_IMAGE_SIZES:
        size = DEFAULT_AI_IMAGE_SIZE

    # Every generation is reshaped into a fuller photographic brief before it
    # reaches Gemini — a site owner's bare "a nice photo for my bakery" is
    # honest but not the professional prompt that produces a sharp, on-brand
    # image. style/mood (wizard chips or free text) become explicit clauses;
    # omitted ones degrade to a generic "fits a professional business site"
    # direction — never a no-op passthrough of the raw prompt. The user's OWN
    # words (`prompt`) still go to `cappe_assets` below unmodified — what they
    # asked for, not what we sent the model.
    gemini_prompt = build_image_prompt(prompt, style=body.style, mood=body.mood)

    try:
        url = await generate_image(
            gemini_prompt, prefix="cappe/gen", aspect_ratio=body.aspect_ratio, image_size=size,
        )
    except ImageGenError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't generate an image for that prompt — try rephrasing it.",
        )
    try:
        async with get_connection() as conn:
            await cappe_assets.record(
                conn, account_id=account.id, site_id=site["id"], kind="generated", url=url,
                prompt=prompt, aspect=body.aspect_ratio, image_size=size,
            )
    except Exception as exc:  # noqa: BLE001 — catalog bookkeeping never fails the generation
        logger.warning("cappe asset catalog insert failed (generate): %s", exc)
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

    if file.content_type not in upload_guard.ALLOWED_DELIVERABLE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    data = await read_capped(file, _MAX_DELIVERABLE_BYTES, "File too large (max 25 MB)")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    content_type = upload_guard.verify_upload(data, file.content_type, upload_guard.ALLOWED_DELIVERABLE)
    url = await get_storage().upload_file(
        file_bytes=data,
        filename=file.filename or "deliverable",
        prefix="cappe",
        content_type=content_type,
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
    if not is_premium_plan(account.plan):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hero video is a premium feature. Upgrade to Pro to add a background video.",
        )

    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)

    if file.content_type not in upload_guard.ALLOWED_VIDEO:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported video type (use MP4, WebM, or MOV)")

    data = await read_capped(file, _MAX_VIDEO_BYTES, "Video too large (max 50 MB)")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    content_type = upload_guard.verify_upload(data, file.content_type, upload_guard.ALLOWED_VIDEO)
    url = await get_storage().upload_file(
        file_bytes=data,
        filename=file.filename or "hero-video",
        prefix="cappe",
        content_type=content_type,
    )
    return CappeUploadResponse(url=url)


@router.get("/sites/{site_id}/assets", response_model=CappeAssetList)
async def list_site_assets(
    site_id: UUID,
    kind: Optional[str] = Query(default=None, pattern="^(generated|upload|stock)$"),
    q: Optional[str] = Query(default=None, max_length=100),
    account: CappeAccount = Depends(require_cappe_account),
):
    """The site's image asset library — everything generated, uploaded or
    imported for it, newest first. Backs the editor's image-field "Library"
    picker, Merlin's "from library" attach and the magazine's Library page."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await cappe_assets.list_assets(conn, site_id, kind=kind, q=(q or "").strip() or None)
    return CappeAssetList(assets=[CappeAsset(**r) for r in rows])


@router.post("/sites/{site_id}/assets/upload", response_model=CappeAsset, status_code=status.HTTP_201_CREATED)
async def upload_library_image(
    site_id: UUID,
    file: UploadFile = File(...),
    rights_attested: bool = Form(...),
    ai_made: bool = Form(False),
    alt: Optional[str] = Form(default=None, max_length=500),
    caption: Optional[str] = Form(default=None, max_length=1000),
    credit_line: Optional[str] = Form(default=None, max_length=500),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Add a picture to the library with what a story prints beside it.

    The owner must say they took it or may use it (`rights_attested`); an
    AI-made picture is credited "AI illustration" whatever else is typed. It is
    stored with its responsive sizes, and — unlike the editor's quick upload —
    the library row is the point, so a failed insert fails the request."""
    if not rights_attested:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Confirm you took this picture or have permission to use it.",
        )
    await check_rate_limit(str(account.id), "cappe_library_upload", 200, 3600)
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)

    if file.content_type not in upload_guard.ALLOWED_IMAGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image type")
    data = await read_capped(file, _MAX_LIBRARY_BYTES, "Image too large (max 15 MB)")
    content_type = upload_guard.verify_upload(data, file.content_type, upload_guard.ALLOWED_IMAGE)
    image = await _process(data, content_type, derivatives=True)
    stored = await media.store_processed(image, prefix="cappe/library", filename=file.filename)

    async with get_connection() as conn:
        asset = await cappe_assets.insert_upload(
            conn, account_id=account.id, site_id=site["id"], url=stored.url,
            width=stored.width, height=stored.height, size_bytes=stored.bytes, mime=stored.mime,
            variants=stored.variants, alt=_text(alt), caption=_text(caption),
            credit_line=_text(credit_line), ai_made=ai_made,
        )
    return CappeAsset(**asset)


def _text(value: Optional[str]) -> Optional[str]:
    return (value or "").strip() or None


@router.patch("/sites/{site_id}/assets/{asset_id}", response_model=CappeAsset)
async def update_site_asset(
    site_id: UUID,
    asset_id: UUID,
    body: CappeAssetPatch,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Edit a library picture's alt text and caption — and, on the owner's own
    uploads, its credit. An archive image's credit comes from its license and
    an AI image is always credited as AI, so those are 422."""
    changes = body.model_dump(exclude_unset=True)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        asset = await cappe_assets.get_asset(conn, site_id, asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        try:
            fields = cappe_assets.editable_fields(asset, changes)
        except cappe_assets.NotEditable as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"This picture's credit comes from its source and can't be changed ({exc}).",
            ) from exc
        updated = await cappe_assets.update_asset(conn, site_id, asset_id, fields)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return CappeAsset(**updated)


@router.delete("/sites/{site_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site_asset(
    site_id: UUID,
    asset_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Remove one asset from the library. Deletes the catalog row only — the
    S3 object stays (a live page may still reference its URL); see
    services/cappe_assets.py."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        deleted = await cappe_assets.delete_asset(conn, site_id, asset_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
