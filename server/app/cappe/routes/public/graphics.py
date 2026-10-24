"""The Studio's built-in graphics (`services/magazine/studio/graphics.py`),
served from our own origin like its faces (`fonts.py`): the Studio shows
them and a reader's page draws them, as a mask or a background.

  * `GET /public/graphics/browse`: each group's first graphics, its count and
    the sticker sets, for the side panel to open on;
  * `GET /public/graphics/search?q=&group=&set=&offset=&limit=`: matches,
    best first;
  * `GET /public/graphics/licenses.txt`: the sources' licences, kept with them;
  * `GET /public/graphics/picks`: the Gummfit-curated bank's live graphics
    (`studio/bank.py`), cached five minutes so an admin's change shows soon;
  * `GET /public/graphics/{sha}.svg`: a file, by its sha256, only one in the
    committed manifest or the curated bank, checked against its sha and cached
    for a year. It is
    sent with a CSP that runs nothing (the files are cleaned when built);
  * `GET /public/graphics/stretch/{sha}.svg`: the same file made to fill any
    box out of its own shape, for the "stretch" fit (`graphics.stretched`).

Files are read from `CAPPE_GRAPHICS_DIR` when it is set (a local build of
`scripts/build_studio_graphics.py`), else from storage
(`cappe/graphics/<sha>.svg`, where the curated bank's go too), and kept in
memory once read.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from ....core.services.storage import get_storage
from ....database import get_connection
from ...services.magazine.studio import bank, graphics

router = APIRouter()

_KEEP = 2_000  # files kept in memory (a few KB each)
_cache: OrderedDict[str, bytes] = OrderedDict()
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}
_SVG_HEADERS = {**_IMMUTABLE, "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
                "X-Content-Type-Options": "nosniff"}
_LISTS = {"Cache-Control": "public, max-age=3600"}
_PICKS = {"Cache-Control": "public, max-age=300"}


def _local(sha: str) -> Optional[bytes]:
    root = os.environ.get("CAPPE_GRAPHICS_DIR")
    if not root:
        return None
    path = Path(root) / f"{sha}.svg"
    return path.read_bytes() if path.is_file() else None


async def graphic_bytes(sha: str) -> Optional[bytes]:
    if sha in _cache:
        _cache.move_to_end(sha)
        return _cache[sha]
    data = await asyncio.to_thread(_local, sha) or await get_storage().get_key(graphics.GRAPHIC_KEY.format(sha=sha))
    if data is None or hashlib.sha256(data).hexdigest() != sha:
        return None
    _cache[sha] = data
    while len(_cache) > _KEEP:
        _cache.popitem(last=False)
    return data


@router.get("/public/graphics/browse")
async def browse_graphics():
    return JSONResponse(graphics.browse(), headers=_LISTS)


@router.get("/public/graphics/search")
async def search_graphics(q: str = Query("", max_length=100), group: Optional[str] = Query(None, max_length=20),
                          set: Optional[str] = Query(None, max_length=40),  # noqa: A002 (the query's name)
                          offset: int = Query(0, ge=0, le=10_000), limit: int = Query(60, ge=1, le=graphics.SEARCH_MAX)):
    if group and group not in graphics.GROUPS:
        raise HTTPException(status_code=422, detail="No such group")
    return JSONResponse(graphics.search(q, group, set, offset, limit), headers=_LISTS)


@router.get("/public/graphics/picks")
async def graphic_picks():
    async with get_connection() as conn:
        picks = await bank.graphic_picks(conn)
    return JSONResponse({"items": picks}, headers=_PICKS)


@router.get("/public/graphics/licenses.txt")
async def graphics_licenses():
    try:
        text = graphics.MANIFEST.with_name("graphics_licenses.txt").read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No licences file") from exc
    return PlainTextResponse(text, headers=_LISTS)


async def _known(sha: str) -> bool:
    if graphics.by_sha(sha) is not None or sha in _cache:
        return True
    if not graphics.is_sha(sha):
        return False
    async with get_connection() as conn:
        return await bank.has_graphic(conn, sha)


async def _file(sha: str) -> bytes:
    if not await _known(sha):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such graphic")
    data = await graphic_bytes(sha)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This graphic hasn't been uploaded yet")
    return data


@router.get("/public/graphics/{sha}.svg")
async def graphic_file(sha: str):
    return Response(await _file(sha), media_type="image/svg+xml", headers=_SVG_HEADERS)


@router.get("/public/graphics/stretch/{sha}.svg")
async def stretched_graphic_file(sha: str):
    return Response(graphics.stretched(await _file(sha)), media_type="image/svg+xml", headers=_SVG_HEADERS)
