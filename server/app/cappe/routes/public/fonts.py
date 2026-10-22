"""The Studio's faces, served from our own origin (`services/magazine/studio/
fonts.py`): the Studio measures and shows them, and a reader's page loads
them, so neither needs another origin's fonts or CORS.

A face is addressed by its sha256, so its bytes never change: it is cached
for a year, and checked against its sha before it is served. Only faces in
the committed manifest are served. The bytes are read from `CAPPE_FONTS_DIR`
when it is set (a local build, `scripts/build_magazine_fonts.py`), else from
storage (`cappe/fonts/<sha>.ttf`, uploaded by the same script), and kept in
memory once read.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, Response

from ....core.services.storage import get_storage
from ...services.magazine.studio.fonts import by_sha, manifest

router = APIRouter()

FONT_KEY = "cappe/fonts/{sha}.ttf"
_KEEP = 160  # faces kept in memory (~100 KB each)
_cache: OrderedDict[str, bytes] = OrderedDict()
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def _local(sha: str) -> Optional[bytes]:
    root = os.environ.get("CAPPE_FONTS_DIR")
    if not root:
        return None
    path = Path(root) / f"{sha}.ttf"
    return path.read_bytes() if path.is_file() else None


async def font_bytes(sha: str) -> Optional[bytes]:
    if sha in _cache:
        _cache.move_to_end(sha)
        return _cache[sha]
    data = await asyncio.to_thread(_local, sha) or await get_storage().get_key(FONT_KEY.format(sha=sha))
    if data is None or hashlib.sha256(data).hexdigest() != sha:
        return None
    _cache[sha] = data
    while len(_cache) > _KEEP:
        _cache.popitem(last=False)
    return data


@router.get("/public/fonts/manifest.json")
async def fonts_manifest():
    return JSONResponse(manifest(), headers={"Cache-Control": "public, max-age=3600"})


@router.get("/public/fonts/{sha}.ttf")
async def font_file(sha: str):
    if by_sha(sha) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such face")
    data = await font_bytes(sha)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This face hasn't been uploaded yet")
    return Response(data, media_type="font/ttf", headers=_IMMUTABLE)
