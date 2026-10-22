"""Cappe social — exports: a dropped video cut for each platform to download.

TikTok and YouTube can't be posted to through their APIs yet, so the owner
downloads a file made for each (and one for Instagram) and uploads it by
hand. The chat makes these from "prepare this for all platforms"; this
router is the Exports tab: list them, start one for a video uploaded there,
download a file (a short presigned link that saves it under a readable
name), and delete.

The work happens on the worker, one step per run
(`workers/tasks/cappe_social_media.py:prepare_cappe_social_export`). Gates:
`social` and `social_video` (the same plan feature as posting a video).
"""
from __future__ import annotations

import logging
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeSocialExport,
    CappeSocialExportCreate,
    CappeSocialExportDownload,
    ExportTarget,
)
from ..services.entitlements import resolve_entitlements
from ..services.social import assets as asset_store
from ..services.social import exports as export_store
from ..services.social import presets
from ._shared import get_owned_site
from .social import _social_gate, _video_gate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sites/{site_id}/social/exports")

_EXPORTS_PER_HOUR = 20


def view(export: dict, asset: Optional[dict]) -> CappeSocialExport:
    return CappeSocialExport(**export_store.public_view(export, asset))


async def views(conn, exports: list[dict]) -> list[CappeSocialExport]:
    assets = await asset_store.load_many(conn, list({e["asset_id"] for e in exports}))
    return [view(e, assets.get(str(e["asset_id"]))) for e in exports]


def queue(export_ids: list) -> None:
    """Start exports once the rows are committed."""
    if not export_ids:
        return
    try:
        from app.workers.tasks.cappe_social_media import queue_exports

        queue_exports(export_ids)
    except Exception:  # noqa: BLE001 — the media sweep starts an export nobody picked up
        logger.warning("cappe social exports: could not queue %s; the sweep will", export_ids, exc_info=True)


@router.get("", response_model=list[CappeSocialExport])
async def list_exports(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        _social_gate(ent)
        return await views(conn, await export_store.list_for_site(conn, site_id))


@router.post("", response_model=CappeSocialExport, status_code=status.HTTP_201_CREATED)
async def create_export(site_id: UUID, body: CappeSocialExportCreate,
                        account: CappeAccount = Depends(require_cappe_account)):
    """Prepare an uploaded video for download. It may still be being cut for
    posting; the export doesn't wait for that."""
    await check_rate_limit(str(account.id), "cappe_social_export", _EXPORTS_PER_HOUR, 3600)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        _social_gate(ent)
        _video_gate(ent)
        asset = await asset_store.get(conn, site_id, body.asset_id)
        if asset is None or asset["status"] not in ("rendering", "ready"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=(asset or {}).get("error") or "That video isn't ready to use")
        export = await export_store.create(
            conn, site_id=site_id, account_id=account.id, asset_id=asset["id"], platforms=list(body.platforms),
            captions=body.captions, texts={}, provenance={"source": "exports_tab"},
        )
    queue([export["id"]])
    return view(export, asset)


@router.get("/{export_id}", response_model=CappeSocialExport)
async def get_export(site_id: UUID, export_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        export = await export_store.get(conn, site_id, export_id)
        if export is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
        asset = await asset_store.get_by_id(conn, export["asset_id"])
    return view(export, asset)


@router.get("/{export_id}/download", response_model=CappeSocialExportDownload)
async def download_export(site_id: UUID, export_id: UUID, target: ExportTarget = Query(...),
                          account: CappeAccount = Depends(require_cappe_account)):
    """A link that saves one file: a platform's cut, the original, or the
    captions (`.srt`)."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        export = await export_store.get(conn, site_id, export_id)
        if export is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
        asset = await asset_store.get_by_id(conn, export["asset_id"])
    bucket = None
    if target == "original":
        if asset is None or asset["status"] == "deleted":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The original is gone")
        bucket, key = asset_store.source_location(asset)
        ext = os.path.splitext(asset.get("filename") or "")[1] or asset_store.VIDEO_TYPES.get(asset["content_type"], "")
        content_type = asset["content_type"]
    elif target == "captions":
        key = (export.get("srt") or {}).get("key")
        ext, content_type = ".srt", "application/x-subrip"
    else:
        if target not in export["platforms"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=f"This export has no {presets.LABELS[target]} file")
        output = (export.get("outputs") or {}).get((export.get("targets") or {}).get(target) or "") or {}
        key = output.get("key") or asset_store.public_key(output.get("url"))
        ext, content_type = ".mp4", "video/mp4"
    if not key:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That file isn't ready yet")
    filename = presets.download_name(site.get("name"), (asset or {}).get("filename"), target, ext)
    try:
        url = asset_store.download_url(key, filename=filename, content_type=content_type, bucket=bucket)
    except asset_store.AssetStorageUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return CappeSocialExportDownload(url=url, filename=filename, expires_in=asset_store.DOWNLOAD_TTL_SECONDS)


@router.delete("/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_export(site_id: UUID, export_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Remove an export and its own files (a cut shared with the video's
    posting render stays)."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        deleted = await export_store.delete(conn, site_id, export_id)
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    await export_store.delete_files(deleted)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router", "view", "views", "queue"]
