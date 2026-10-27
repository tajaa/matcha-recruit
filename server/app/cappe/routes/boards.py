"""Mood boards (`cappeboard01`, `services/boards/`): a site's pinboards.

The owner pins photos and screenshots, documents, notes and links anywhere on
a board, next to or on top of each other. Everything here is the owner's
alone: answers are `no-store, private`, and a pin's files stay in the private
bucket behind signed links (`services/boards/files.py`).

A pinned picture is reference, not something the owner has said they may
publish. Using one in a story goes through `…/pins/{pin_id}/library`, which
asks the library's question ("I took this or may use it") and makes it a
library picture; the pin then shows that picture.

Network work (storing files, fetching a link's preview) is done with no
connection held, between a quick ownership check and the insert.
"""
import asyncio
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from ...core.services.redis_cache import check_rate_limit
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.boards import (
    BoardDetail,
    BoardList,
    BoardOut,
    BoardTitle,
    Layout,
    LayoutResult,
    PinCreate,
    PinOut,
    PinPatch,
    PinToLibrary,
)
from ..models.cappe import CappeAccount, CappeAsset
from ..services import cappe_assets, media, upload_guard
from ..services.boards import files, links, store
from ..services.boards.limits import COORD_MAX, MAX_FILE_BYTES, SIZE_MAX, SIZE_MIN
from ._shared import get_owned_site, read_capped

logger = logging.getLogger(__name__)

router = APIRouter()

_PRIVATE = {"Cache-Control": "no-store, private"}
READS_PER_HOUR = 1200
WRITES_PER_HOUR = 2400
UPLOADS_PER_HOUR = 200
LINKS_PER_HOUR = 120
NO_STORAGE = "Pinning files isn't available right now. Notes and links still work."
WHAT_PINS = "Pin photos, screenshots, PDFs, Word or Excel files, or text files."


def _private(model) -> JSONResponse:
    return JSONResponse(model.model_dump(mode="json"), headers=_PRIVATE)


def _text(value: Optional[str]) -> Optional[str]:
    return (value or "").strip() or None


def _clamp(value: float) -> float:
    return max(SIZE_MIN, min(SIZE_MAX, value))


def _fit(ratio: float, w: float) -> tuple[float, float]:
    """A box `w` wide in the shape `ratio` (width / height), moved inside the
    size bounds without changing its shape. Only a picture longer than
    SIZE_MAX:SIZE_MIN can't keep it."""
    h = w / ratio
    if h > SIZE_MAX:
        h, w = SIZE_MAX, SIZE_MAX * ratio
    if h < SIZE_MIN:
        h, w = SIZE_MIN, SIZE_MIN * ratio
    return round(_clamp(w), 1), round(_clamp(h), 1)


def _size(kind: str, *, width: Optional[int] = None, height: Optional[int] = None,
          has_picture: bool = False) -> tuple[float, float]:
    """A new pin's size when the board didn't say: pictures keep their shape."""
    if kind == "image" and width and height:
        return _fit(width / height, 280.0)
    if kind == "note":
        return 220.0, 180.0
    if kind == "link":
        return 280.0, 260.0 if has_picture else 120.0
    if kind == "file":
        return 220.0, 290.0 if has_picture else 120.0
    return 280.0, 280.0


def _placed(body, kind: str, **shape) -> dict:
    """Where a new pin goes. A picture given only one side gets the other
    from its own shape."""
    w, h = _size(kind, **shape)
    width, height = shape.get("width"), shape.get("height")
    if body.w and body.h:
        w, h = body.w, body.h
    elif kind == "image" and width and height and (body.w or body.h):
        ratio = width / height
        w, h = _fit(ratio, body.w or body.h * ratio)
    else:
        w, h = body.w or w, body.h or h
    return {"x": body.x, "y": body.y, "w": w, "h": h, "rotation": body.rotation}


def _limit_error(exc: Exception) -> HTTPException:
    code = status.HTTP_413_CONTENT_TOO_LARGE if isinstance(exc, store.SiteFull) else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=str(exc))


async def _owned_board(conn, site_id: UUID, board_id: UUID, account: CappeAccount) -> dict:
    await get_owned_site(conn, site_id, account.id)
    board = await store.get_board(conn, site_id, board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    return board


async def _insert(site_id: UUID, board_id: UUID, fields: dict, *, cleanup: list[str] = ()) -> dict:
    """Insert a pin; on any refusal, remove the files stored for it."""
    try:
        async with get_connection() as conn:
            return await store.insert_pin(conn, site_id, board_id, fields)
    except store.BoardGone as exc:  # deleted while the file was being stored
        await files.remove(cleanup)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found") from exc
    except (store.BoardLimit, store.SiteFull) as exc:
        await files.remove(cleanup)
        raise _limit_error(exc) from exc
    except Exception:
        await files.remove(cleanup)
        raise


async def _remove_public(stored: media.StoredImage) -> None:
    """Best-effort delete of a stored library picture and all its sizes."""
    urls = [stored.url, *(v["url"] for v in stored.variants.get("webp", [])),
            *([stored.variants["share"]["url"]] if stored.variants.get("share") else [])]
    storage = get_storage()
    results = await asyncio.gather(*(storage.delete_file(u) for u in urls), return_exceptions=True)
    for url, result in zip(urls, results):
        if isinstance(result, Exception) or result is False:
            logger.warning("orphan library copy not deleted: %s (%s)", url, result)


# ── boards ──────────────────────────────────────────────────────────────────

@router.get("/sites/{site_id}/boards", response_model=BoardList)
async def list_boards(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_boards_read", READS_PER_HOUR, 3600)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        boards = await store.list_boards(conn, site_id)
    return _private(BoardList(boards=[BoardOut(**b) for b in boards]))


@router.post("/sites/{site_id}/boards", response_model=BoardOut, status_code=status.HTTP_201_CREATED)
async def create_board(site_id: UUID, body: BoardTitle, account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_boards_write", WRITES_PER_HOUR, 3600)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        try:
            board = await store.create_board(conn, site_id, body.title)
        except store.BoardLimit as exc:
            raise _limit_error(exc) from exc
    return JSONResponse(BoardOut(**board).model_dump(mode="json"), status_code=status.HTTP_201_CREATED,
                        headers=_PRIVATE)


@router.get("/sites/{site_id}/boards/{board_id}", response_model=BoardDetail)
async def get_board(site_id: UUID, board_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_boards_read", READS_PER_HOUR, 3600)
    async with get_connection() as conn:
        board = await _owned_board(conn, site_id, board_id, account)
        pins = await store.list_pins(conn, board_id)
        assets = await store.library_assets(conn, site_id, pins)
    covers = [p["src"] for p in sorted(pins, key=lambda p: -p["z"]) if p["src"]][: store.COVERS]
    return _private(BoardDetail(board=BoardOut(**board, pin_count=len(pins), covers=covers),
                                pins=[PinOut(**p) for p in pins], assets=[CappeAsset(**a) for a in assets]))


@router.patch("/sites/{site_id}/boards/{board_id}", response_model=BoardOut)
async def rename_board(site_id: UUID, board_id: UUID, body: BoardTitle,
                       account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_boards_write", WRITES_PER_HOUR, 3600)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        board = await store.rename_board(conn, site_id, board_id, body.title)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    return _private(BoardOut(**board))


@router.delete("/sites/{site_id}/boards/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(site_id: UUID, board_id: UUID, background: BackgroundTasks,
                       account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_boards_write", WRITES_PER_HOUR, 3600)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        held = await store.delete_board(conn, site_id, board_id)
    if held is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    background.add_task(files.remove, held)


# ── pins ────────────────────────────────────────────────────────────────────

@router.post("/sites/{site_id}/boards/{board_id}/pins", response_model=PinOut, status_code=status.HTTP_201_CREATED)
async def create_pin(site_id: UUID, board_id: UUID, body: PinCreate,
                     account: CappeAccount = Depends(require_cappe_account)):
    """A note, a link (its preview fetched now), or a library picture."""
    await check_rate_limit(str(account.id), "cappe_boards_write", WRITES_PER_HOUR, 3600)
    async with get_connection() as conn:
        await _owned_board(conn, site_id, board_id, account)
        if body.kind == "image":
            asset = await cappe_assets.get_asset(conn, site_id, body.asset_id)
            if asset is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail="That picture isn't in this site's library.")
        if body.kind == "link":
            try:
                await store.check_room(conn, site_id, board_id, 0)
            except (store.BoardLimit, store.SiteFull) as exc:
                raise _limit_error(exc) from exc

    if body.kind == "note":
        fields = {"kind": "note", **_placed(body, "note"), "note": body.note.strip(), "color": body.color or "yellow"}
        pin = await _insert(site_id, board_id, fields)
    elif body.kind == "image":
        fields = {"kind": "image", **_placed(body, "image", width=asset["width"], height=asset["height"]),
                  "asset_id": body.asset_id}
        pin = await _insert(site_id, board_id, fields)
    else:
        pin = await _pin_link(account, site_id, board_id, body)
    return JSONResponse(PinOut(**pin).model_dump(mode="json"), status_code=status.HTTP_201_CREATED,
                        headers=_PRIVATE)


async def _pin_link(account: CappeAccount, site_id: UUID, board_id: UUID, body: PinCreate) -> dict:
    try:
        url = links.normalize_url(body.url or "")
    except links.BadLink as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    await check_rate_limit(str(account.id), "cappe_boards_link", LINKS_PER_HOUR, 3600)
    preview = await links.fetch_preview(url)
    stored: list[str] = []
    try:
        if preview.direct and preview.image_bytes:
            try:
                picture = await files.store_image(preview.image_bytes, preview.image_mime, url.rsplit("/", 1)[-1])
            except media.ImageRejected:
                picture = None
            if picture:
                stored = [picture.file_path, picture.thumb_path]
                fields = {"kind": "image", **_placed(body, "image", width=picture.width, height=picture.height),
                          "file_path": picture.file_path, "thumb_path": picture.thumb_path,
                          "filename": picture.filename, "mime": picture.mime, "size_bytes": picture.size_bytes,
                          "width": picture.width, "height": picture.height, "url": url,
                          "title": links.host_of(url)}
                return await _insert(site_id, board_id, fields, cleanup=stored)
        thumb_path, thumb_bytes = None, 0
        if preview.image_bytes and not preview.direct:
            thumb_path, thumb_bytes = await files.store_thumbnail(preview.image_bytes)
            stored = [thumb_path]
    except files.StorageUnavailable:
        thumb_path, thumb_bytes, stored = None, 0, []
    fields = {"kind": "link", **_placed(body, "link", has_picture=bool(thumb_path)), "url": url,
              "title": preview.title, "description": preview.description, "site_name": preview.site_name,
              "thumb_path": thumb_path, "size_bytes": thumb_bytes, "mime": "image/webp" if thumb_path else None}
    return await _insert(site_id, board_id, fields, cleanup=stored)


@router.post("/sites/{site_id}/boards/{board_id}/pins/upload", response_model=PinOut,
             status_code=status.HTTP_201_CREATED)
async def upload_pin(
    site_id: UUID,
    board_id: UUID,
    file: UploadFile = File(...),
    x: float = Form(..., ge=-COORD_MAX, le=COORD_MAX),
    y: float = Form(..., ge=-COORD_MAX, le=COORD_MAX),
    account: CappeAccount = Depends(require_cappe_account),
):
    """A photo, a screenshot or a document, dropped or pasted at (x, y)."""
    await check_rate_limit(str(account.id), "cappe_boards_upload", UPLOADS_PER_HOUR, 3600)
    declared = files.declared_type(file.content_type, file.filename)
    if declared not in files.IMAGE_TYPES and declared not in files.DOCUMENT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=WHAT_PINS)
    async with get_connection() as conn:
        await _owned_board(conn, site_id, board_id, account)
        try:
            await store.check_room(conn, site_id, board_id, 1)
        except (store.BoardLimit, store.SiteFull) as exc:
            raise _limit_error(exc) from exc
    data = await read_capped(file, MAX_FILE_BYTES, f"Pinned files can be {MAX_FILE_BYTES // (1024 * 1024)} MB at most.")
    is_image = declared in files.IMAGE_TYPES
    mime = upload_guard.verify_upload(data, declared, files.IMAGE_TYPES if is_image else files.DOCUMENT_TYPES)
    if mime == "text/plain" and declared == "text/csv":
        mime = "text/csv"
    try:
        if is_image:
            kept = await files.store_image(data, mime, file.filename)
        else:
            kept = await files.store_document(data, mime, file.filename)
    except media.ImageRejected as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except files.StorageUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=NO_STORAGE) from exc
    kind = "image" if is_image else "file"
    place = _size(kind, width=kept.width, height=kept.height, has_picture=bool(kept.thumb_path))
    fields = {"kind": kind, "x": x, "y": y, "w": place[0], "h": place[1], "rotation": 0,
              "file_path": kept.file_path, "thumb_path": kept.thumb_path, "filename": kept.filename,
              "mime": kept.mime, "size_bytes": kept.size_bytes, "width": kept.width, "height": kept.height}
    pin = await _insert(site_id, board_id, fields, cleanup=[kept.file_path, kept.thumb_path])
    return JSONResponse(PinOut(**pin).model_dump(mode="json"), status_code=status.HTTP_201_CREATED,
                        headers=_PRIVATE)


@router.patch("/sites/{site_id}/boards/{board_id}/pins/{pin_id}", response_model=PinOut)
async def update_pin(site_id: UUID, board_id: UUID, pin_id: UUID, body: PinPatch,
                     account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_boards_write", WRITES_PER_HOUR, 3600)
    changes = body.model_dump(exclude_unset=True)
    for key in ("x", "y", "w", "h", "rotation", "z", "color"):
        if key in changes and changes[key] is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{key} can't be empty")
    async with get_connection() as conn:
        await _owned_board(conn, site_id, board_id, account)
        row = await store.get_pin(conn, board_id, pin_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pin not found")
        if "note" in changes:
            text = (changes["note"] or "").strip()
            if row["kind"] == "note" and not text:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail="A note needs words. Delete it instead.")
            changes["note"] = text or None
        if "title" in changes:
            changes["title"] = " ".join((changes["title"] or "").split()) or None
        if "color" in changes and row["kind"] != "note":
            changes.pop("color")
        pin = await store.update_pin(conn, site_id, board_id, pin_id, changes)
    if pin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pin not found")
    return _private(PinOut(**pin))


@router.put("/sites/{site_id}/boards/{board_id}/layout", response_model=LayoutResult)
async def update_layout(site_id: UUID, board_id: UUID, body: Layout,
                        account: CappeAccount = Depends(require_cappe_account)):
    """Where many pins now are: after a drag, a resize or a raise."""
    await check_rate_limit(str(account.id), "cappe_boards_write", WRITES_PER_HOUR, 3600)
    items = [i.model_dump() for i in body.pins]
    if len({i["id"] for i in items}) != len(items):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A pin is listed twice")
    async with get_connection() as conn:
        await _owned_board(conn, site_id, board_id, account)
        moved = await store.update_layout(conn, site_id, board_id, items)
    return _private(LayoutResult(moved=moved))


@router.delete("/sites/{site_id}/boards/{board_id}/pins/{pin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pin(site_id: UUID, board_id: UUID, pin_id: UUID, background: BackgroundTasks,
                     account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_boards_write", WRITES_PER_HOUR, 3600)
    async with get_connection() as conn:
        await _owned_board(conn, site_id, board_id, account)
        held = await store.delete_pin(conn, site_id, board_id, pin_id)
    if held is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pin not found")
    background.add_task(files.remove, held)


@router.post("/sites/{site_id}/boards/{board_id}/pins/{pin_id}/library")
async def pin_to_library(site_id: UUID, board_id: UUID, pin_id: UUID, body: PinToLibrary,
                         background: BackgroundTasks, account: CappeAccount = Depends(require_cappe_account)):
    """Make a pinned picture a library picture, so a story can use it. Asks
    what the library upload asks; the pin then shows the library's copy."""
    if not body.rights_attested:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Confirm you took this picture or have permission to use it.")
    await check_rate_limit(str(account.id), "cappe_library_upload", 200, 3600)
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        if await store.get_board(conn, site_id, board_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
        row = await store.get_pin(conn, board_id, pin_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pin not found")
    if row["kind"] != "image" or not row["file_path"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Only a pinned picture that isn't in the library yet can be added.")
    try:
        data = await get_storage().download_file(row["file_path"])
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=NO_STORAGE) from exc
    try:
        image = await asyncio.to_thread(media.process_image, data, row["mime"] or "image/jpeg", derivatives=True)
    except media.ImageRejected as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    try:
        stored = await media.store_processed(image, prefix="cappe/library", filename=row["filename"])
    except RuntimeError as exc:  # S3 refused or isn't set up
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=NO_STORAGE) from exc
    try:
        async with get_connection() as conn:
            async with conn.transaction():
                asset = await cappe_assets.insert_upload(
                    conn, account_id=account.id, site_id=site["id"], url=stored.url, width=stored.width,
                    height=stored.height, size_bytes=stored.bytes, mime=stored.mime, variants=stored.variants,
                    alt=_text(body.alt), caption=None, credit_line=_text(body.credit_line), ai_made=body.ai_made,
                )
                pin = await store.attach_asset(conn, site_id, board_id, pin_id, asset["id"], row["file_path"])
                if pin is None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                        detail="That pin changed meanwhile. Open the board again and retry.")
    except Exception:
        # Nothing records the public copy just made (the insert rolled back):
        # take it down rather than leave a reachable orphan on the CDN.
        await _remove_public(stored)
        raise
    background.add_task(files.remove, [row["file_path"], row["thumb_path"]])
    return JSONResponse({"pin": PinOut(**pin).model_dump(mode="json"),
                         "asset": CappeAsset(**asset).model_dump(mode="json")}, headers=_PRIVATE)
