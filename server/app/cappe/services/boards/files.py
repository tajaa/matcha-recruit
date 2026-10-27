"""A pin's own files: private storage, and the signed links that show them.

A mood board is mostly other people's work kept for reference, so a pin's
files go to the private bucket (`StorageService.upload_private_file`), never
the public CDN, and nothing about them is public until the owner adds a
picture to the library ("I may use this").

The dashboard's CSP loads images only from our origin and CloudFront, and an
`<img>` can't carry the bearer token, so a pin's picture is
`/public/board-files/<token>` under the Cappe API. The token names only the
pin and which of its files (thumbnail, full picture, document) with an
expiry, signed with the app's secret (`services/signed_links.py`, as archive
thumbnails are): a token's payload is readable, so it never carries a storage
path; the route looks the file up by pin. A deleted pin's links die with it.
Pictures are streamed from our origin; a document redirects to a short
presigned S3 link carrying its own name, so its bytes never pass through us or
open on our origin.

Expiries are rounded to a window (`_expiry`), so the same picture keeps the
same link for hours and the browser's cache works across board loads.

A PDF's first page is drawn on a small pool of its own with a time limit
(`first_page`), so a hostile PDF can hold at most those threads, never the
shared pool every request's other work runs on.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import quote
from uuid import UUID

from PIL import Image

from ....core.services.storage import get_storage
from .. import media, signed_links, upload_guard
from .limits import FILENAME_MAX

logger = logging.getLogger(__name__)

PREFIX = "cappe/boards"
PATH = "/public/board-files/"
TTL_SECONDS = 6 * 3600
THUMB_SIDE = 800
PDF_THUMB_ZOOM = 1.5
PDF_SECONDS = 10.0
PURPOSE = b"cappe-board-file"
PARTS = ("thumb", "full", "doc")
_PDF_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cappe-board-pdf")

IMAGE_TYPES = set(upload_guard.ALLOWED_IMAGE)
PDF = "application/pdf"
DOCUMENT_TYPES = {
    PDF,
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
}
# What a browser sends for a file it can't name: the extension decides instead.
_BY_EXTENSION = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".pdf": PDF, ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain", ".md": "text/plain", ".csv": "text/csv",
}
_VAGUE = {"", "application/octet-stream", "binary/octet-stream"}


class StorageUnavailable(RuntimeError):
    """There is no private bucket to keep pins in."""


@dataclass(frozen=True)
class StoredFile:
    file_path: Optional[str]
    thumb_path: Optional[str]
    mime: str
    size_bytes: int
    filename: str
    width: Optional[int] = None
    height: Optional[int] = None


# ── naming ──────────────────────────────────────────────────────────────────

def clean_filename(name: Optional[str], fallback: str = "file") -> str:
    """The upload's own name, safe to show and to put in a header: no path, no
    control characters, at most `FILENAME_MAX` characters (extension kept)."""
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = "".join(c for c in base if unicodedata.category(c)[0] != "C")
    if not base or base in (".", ".."):
        return fallback
    if len(base) > FILENAME_MAX:
        stem, ext = os.path.splitext(base)
        ext = ext[:16]
        base = stem[: FILENAME_MAX - len(ext)] + ext
    return base


def declared_type(content_type: Optional[str], filename: Optional[str]) -> Optional[str]:
    """The type to check the bytes against. A vague one (no type, octet-stream)
    goes by the extension; a CSV that Windows calls an Excel file is a CSV."""
    declared = (content_type or "").split(";")[0].strip().lower()
    ext = os.path.splitext(filename or "")[1].lower()
    if declared in _VAGUE:
        return _BY_EXTENSION.get(ext)
    if declared == "application/vnd.ms-excel" and ext == ".csv":
        return "text/csv"
    return declared


def disposition(filename: str, mime: str) -> str:
    """How S3 should answer a document: a PDF or text opens in the tab, anything
    else downloads; always under its own name."""
    how = "inline" if mime in (PDF, "text/plain") else "attachment"
    ascii_name = filename.encode("ascii", "ignore").decode().replace('"', "") or "file"
    return f"{how}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


# ── signed links ────────────────────────────────────────────────────────────

def _expiry(now: float) -> int:
    """Between one and two windows from now, the same for everyone within a
    window: the same file gets the same link, so the browser caches it."""
    return int((now // TTL_SECONDS + 2) * TTL_SECONDS)


def link(pin_id: UUID | str, part: str, *, now: Optional[float] = None) -> str:
    """The signed link to one of a pin's files: `thumb`, `full` or `doc`."""
    claim = {"i": str(pin_id), "f": part, "e": _expiry(time.time() if now is None else now)}
    return PATH + signed_links.sign(PURPOSE, claim)


def verify(token: str, *, now: Optional[float] = None) -> Optional[tuple[UUID, str]]:
    """The (pin id, part) a token stands for, or None when it is forged,
    mangled or expired."""
    claim = signed_links.verify(PURPOSE, token, now=now)
    if claim is None or claim.get("f") not in PARTS or not isinstance(claim.get("i"), str):
        return None
    try:
        return UUID(claim["i"]), claim["f"]
    except ValueError:
        return None


# ── pictures ────────────────────────────────────────────────────────────────

def thumbnail(data: bytes) -> bytes:
    """A WebP no wider or taller than `THUMB_SIDE`, from the first frame, with
    none of the original's metadata. Raises `media.ImageRejected`."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > media.MAX_PIXELS:
                raise media.ImageRejected("That image is too large.")
            img.seek(0)
            frame = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P", "PA") else img.convert("RGB")
    except media.ImageRejected:
        raise
    except Exception as exc:  # Pillow raises a different error per format
        raise media.ImageRejected("That file isn't an image we can read.") from exc
    frame.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    frame.save(out, "WEBP", quality=80, method=4)
    return out.getvalue()


def pdf_thumbnail(data: bytes) -> Optional[bytes]:
    """The first page as a thumbnail, or None when it can't be drawn (an
    encrypted, broken or odd PDF still pins, as a plain file card)."""
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass or doc.page_count < 1:
                return None
            page = doc.load_page(0)
            rect = page.rect
            if rect.width <= 0 or rect.height <= 0:
                return None
            zoom = min(PDF_THUMB_ZOOM, THUMB_SIDE / max(rect.width, rect.height) * 1.5)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            png = pix.tobytes("png")
        return thumbnail(png)
    except Exception as exc:  # noqa: BLE001 — any PDF we can't draw is just a file card
        logger.info("board pdf thumbnail failed: %s", exc)
        return None


async def first_page(data: bytes) -> Optional[bytes]:
    """`pdf_thumbnail` on the PDF pool, or None past `PDF_SECONDS`. The thread
    may run on after a timeout; it holds one of the pool's two, nothing else."""
    try:
        return await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(_PDF_POOL, pdf_thumbnail, data),
                                      PDF_SECONDS)
    except TimeoutError:
        logger.warning("board pdf thumbnail took over %ss; pinned without one", PDF_SECONDS)
        return None


# ── storing ─────────────────────────────────────────────────────────────────

async def _put(data: bytes, filename: str, mime: str) -> str:
    try:
        return await get_storage().upload_private_file(data, filename, prefix=PREFIX, content_type=mime)
    except RuntimeError as exc:  # no S3: the storage service says so this way
        raise StorageUnavailable(str(exc)) from exc


async def store_image(data: bytes, mime: str, filename: Optional[str]) -> StoredFile:
    """Re-encode a picture without its metadata (a phone photo's GPS position
    never reaches storage) and keep it with a thumbnail. Raises
    `media.ImageRejected` or `StorageUnavailable`."""
    image = await asyncio.to_thread(media.process_image, data, mime)
    thumb = await asyncio.to_thread(thumbnail, image.data)
    name = clean_filename(filename, "picture")
    stored_name = media.filename_for(name, image.ext)
    file_path, thumb_path = await asyncio.gather(
        _put(image.data, stored_name, image.mime), _put(thumb, "thumb.webp", "image/webp"),
    )
    return StoredFile(file_path=file_path, thumb_path=thumb_path, mime=image.mime, size_bytes=len(image.data) + len(thumb),
                      filename=stored_name, width=image.width, height=image.height)


async def store_document(data: bytes, mime: str, filename: Optional[str]) -> StoredFile:
    """Keep a document as it came, with its first page drawn when it is a PDF.
    Raises `StorageUnavailable`."""
    name = clean_filename(filename)
    thumb = await first_page(data) if mime == PDF else None
    if thumb:
        file_path, thumb_path = await asyncio.gather(_put(data, name, mime), _put(thumb, "page1.webp", "image/webp"))
    else:
        file_path, thumb_path = await _put(data, name, mime), None
    return StoredFile(file_path=file_path, thumb_path=thumb_path, mime=mime,
                      size_bytes=len(data) + len(thumb or b""), filename=name)


async def store_thumbnail(data: bytes) -> tuple[str, int]:
    """A link's preview picture, already a thumbnail. Returns (path, bytes)."""
    return await _put(data, "preview.webp", "image/webp"), len(data)


async def remove(paths: Iterable[Optional[str]]) -> None:
    """Delete stored files, best effort: a file left behind is only storage,
    and a row is never kept for the sake of its file."""
    targets = [p for p in dict.fromkeys(paths) if p]
    if not targets:
        return
    storage = get_storage()
    results = await asyncio.gather(*(storage.delete_private_file(p) for p in targets), return_exceptions=True)
    for path, result in zip(targets, results):
        if isinstance(result, Exception) or result is False:
            logger.warning("board file not deleted: %s (%s)", path, result)
