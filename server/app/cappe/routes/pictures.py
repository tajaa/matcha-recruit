"""The Studio's Picture Editor (services/magazine/studio/recipe.py, edits.py,
models.py; migration cappemag10).

  * `GET /sites/{id}/assets/{asset_id}/pixels`: a library picture's own file,
    from our origin, for the editor to draw with WebGL (a picture from the CDN
    can't be read into a canvas without CORS). Owner only, never cached.
  * `POST /sites/{id}/assets/{asset_id}/edit`: what the editor made of that
    picture, uploaded as a new library picture (kind `edit`) with the recipe,
    the source as its parent and the source's provenance and licence. The
    upload must be the source edited (edits.size_matches, edits.looks_like).
  * `GET /studio/models/manifest.json` and `/studio/models/{sha}.onnx`: the
    cut-out model's files, for signed-in accounts only.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response
from PIL import Image, UnidentifiedImageError

from ...core.services.redis_cache import check_rate_limit
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeAsset
from ..services import cappe_assets, media, upload_guard
from ..services.magazine.studio import edits, models
from ..services.magazine.studio.recipe import normalize_recipe
from ._shared import get_owned_site, read_capped

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_EDIT_BYTES = 25 * 1024 * 1024  # a 3200 px PNG with its cut-out
_NO_STORE = {"Cache-Control": "private, no-store"}
_IMMUTABLE = {"Cache-Control": "private, max-age=31536000, immutable"}
NOT_AN_EDIT = "This isn't that picture edited, so it can't keep its credit and licence. Upload it to the library instead."


async def _owned_asset(conn, site_id: UUID, asset_id: UUID, account_id: UUID) -> dict:
    await get_owned_site(conn, site_id, account_id)
    asset = await cappe_assets.get_asset(conn, site_id, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Picture not found")
    return asset


async def _source_bytes(asset: dict) -> bytes:
    try:
        return await get_storage().download_file(asset["url"])
    except Exception as exc:
        logger.warning("picture %s: couldn't read its file: %s", asset["id"], exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Couldn't read that picture's file.") from exc


@router.get("/sites/{site_id}/assets/{asset_id}/pixels")
async def picture_pixels(site_id: UUID, asset_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_picture_pixels", 600, 3600)
    async with get_connection() as conn:
        asset = await _owned_asset(conn, site_id, asset_id, account.id)
    data = await _source_bytes(asset)
    return Response(data, media_type=asset.get("mime") or "image/jpeg", headers=_NO_STORE)


def _size(data: bytes) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            return img.size
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That isn't a picture.") from exc


@router.post("/sites/{site_id}/assets/{asset_id}/edit", response_model=CappeAsset, status_code=status.HTTP_201_CREATED)
async def save_picture_edit(
    site_id: UUID,
    asset_id: UUID,
    file: UploadFile = File(...),
    recipe: str = Form(..., max_length=20_000),
    account: CappeAccount = Depends(require_cappe_account),
):
    await check_rate_limit(str(account.id), "cappe_picture_edit", 120, 3600)
    try:
        clean = normalize_recipe(json.loads(recipe))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The recipe isn't JSON.") from exc
    async with get_connection() as conn:
        source = await _owned_asset(conn, site_id, asset_id, account.id)

    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image type")
    data = await read_capped(file, _MAX_EDIT_BYTES, "Image too large (max 25 MB)")
    content_type = upload_guard.verify_upload(data, file.content_type, upload_guard.ALLOWED_IMAGE)
    width, height = await asyncio.to_thread(_size, data)
    if not edits.size_matches(source, width, height, clean):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=NOT_AN_EDIT)
    original = await _source_bytes(source)
    if not await asyncio.to_thread(edits.looks_like, original, data, clean):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=NOT_AN_EDIT)
    try:
        image = await asyncio.to_thread(media.process_image, data, content_type, derivatives=True)
    except media.ImageRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    stored = await media.store_processed(image, prefix="cappe/library", filename="edited")

    async with get_connection() as conn:
        asset = await edits.insert_edit(
            conn, account_id=account.id, site_id=site_id, source=source, recipe=clean, url=stored.url,
            width=stored.width, height=stored.height, size_bytes=stored.bytes, mime=stored.mime,
            variants=stored.variants,
        )
    return CappeAsset(**asset)


@router.get("/studio/models/manifest.json")
async def models_manifest(account: CappeAccount = Depends(require_cappe_account)):
    return JSONResponse(models.manifest(), headers={"Cache-Control": "private, max-age=3600"})


@router.get("/studio/models/{sha}.onnx")
async def model_file(sha: str, account: CappeAccount = Depends(require_cappe_account)):
    if models.by_sha(sha) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such model")
    data = await models.model_bytes(sha)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This model hasn't been uploaded yet")
    return Response(data, media_type="application/octet-stream", headers=_IMMUTABLE)
