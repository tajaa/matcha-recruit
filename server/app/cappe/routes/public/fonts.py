"""The Studio's faces, served from our own origin (`services/magazine/studio/
fonts.py`): the Studio measures and shows them, and a reader's page loads
them, so neither needs another origin's fonts or CORS.

A face is addressed by its sha256, so its bytes never change: it is cached
for a year, and checked against its sha before it is served. Only faces in
the committed manifest, or a magazine's own uploaded faces
(`cappe_studio_fonts`, hidden ones too: pages that set one keep it), are
served. The bytes are read from `CAPPE_FONTS_DIR` when it is set (a local
build, `scripts/build_magazine_fonts.py`), else from storage
(`cappe/fonts/<sha>.ttf`, uploaded by the same script or by
`routes/studio_fonts.py`), and kept in memory once read.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, Response

from ....core.services.storage import get_storage
from ....database import get_connection
from ...services.magazine.studio.custom_fonts import known_sha
from ...services.magazine.studio.fonts import by_sha, manifest

router = APIRouter()

FONT_KEY = "cappe/fonts/{sha}.ttf"
_KEEP = 160  # faces kept in memory (~100 KB each)
_KEEP_MAX_BYTES = 2 * 1024 * 1024  # an uploaded face can be far bigger: those are read from storage each time
_cache: OrderedDict[str, bytes] = OrderedDict()
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_KNOWN_CUSTOM = 4096  # uploaded faces remembered as known (a row is never deleted, so only yes is cached)
_custom: OrderedDict[str, None] = OrderedDict()


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
    if len(data) > _KEEP_MAX_BYTES:
        return data
    _cache[sha] = data
    while len(_cache) > _KEEP:
        _cache.popitem(last=False)
    return data


async def known_face(sha: str) -> bool:
    """Whether `sha` is one of the Studio's faces or a magazine's own."""
    if by_sha(sha) is not None:
        return True
    if not _SHA.match(sha):
        return False
    if sha in _custom:
        _custom.move_to_end(sha)
        return True
    async with get_connection() as conn:
        if not await known_sha(conn, sha):
            return False
    _custom[sha] = None
    while len(_custom) > _KNOWN_CUSTOM:
        _custom.popitem(last=False)
    return True


@router.get("/public/fonts/manifest.json")
async def fonts_manifest():
    return JSONResponse(manifest(), headers={"Cache-Control": "public, max-age=3600"})


@router.get("/public/fonts/{sha}.ttf")
async def font_file(sha: str):
    if not await known_face(sha):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such face")
    data = await font_bytes(sha)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This face hasn't been uploaded yet")
    return Response(data, media_type="font/ttf", headers=_IMMUTABLE)
