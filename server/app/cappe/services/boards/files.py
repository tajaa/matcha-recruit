"""A pin's own files: private storage, and the signed links that show them.

A mood board is mostly other people's work kept for reference, so a pin's
files go to the private bucket (`StorageService.upload_private_file`), never
the public CDN, and nothing about them is public until the owner adds a
picture to the library ("I may use this").

The dashboard's CSP loads images only from our origin and CloudFront, and an
`<img>` can't carry the bearer token, so a pin's picture is
`/public/board-files/<token>` under the Cappe API. The token is the private
path, how to answer and an expiry, signed with the app's secret (as
`magazine/sources/thumbs.py` signs archive thumbnails), so the route serves
only what a board answer of ours handed out. Pictures are streamed from our
origin; a document redirects to a short presigned S3 link carrying its own
name, so its bytes never pass through us or open on our origin.

Expiries are rounded to a window (`_expiry`), so the same picture keeps the
same link for hours and the browser's cache works across board loads.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import time
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import quote

from PIL import Image

from ....config import get_settings
from ....core.services.storage import get_storage
from .. import media, upload_guard
from .limits import FILENAME_MAX

logger = logging.getLogger(__name__)

PREFIX = "cappe/boards"
PATH = "/public/board-files/"
TTL_SECONDS = 6 * 3600
THUMB_SIDE = 800
PDF_THUMB_ZOOM = 1.5

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

def _key() -> bytes:
    return hashlib.sha256(b"cappe-board-file:" + get_settings().jwt_secret_key.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _expiry(now: float) -> int:
    """Between one and two windows from now, the same for everyone within a
    window: the same file gets the same link, so the browser caches it."""
    return int((now // TTL_SECONDS + 2) * TTL_SECONDS)


def sign(path: str, *, mode: str, mime: str, name: Optional[str] = None, now: Optional[float] = None) -> str:
    claim = {"p": path, "m": mode, "t": mime, "e": _expiry(time.time() if now is None else now)}
    if name:
        claim["n"] = name
    payload = _b64(json.dumps(claim, separators=(",", ":")).encode())
    mac = _b64(hmac.new(_key(), payload.encode(), hashlib.sha256).digest()[:18])
    return f"{payload}.{mac}"


def image_link(path: Optional[str], mime: str) -> Optional[str]:
    return PATH + sign(path, mode="image", mime=mime) if path else None


def document_link(path: Optional[str], mime: str, name: str) -> Optional[str]:
    return PATH + sign(path, mode="doc", mime=mime, name=name) if path else None


def verify(token: str, *, now: Optional[float] = None) -> Optional[dict]:
    """What a token stands for (`p` path, `m` mode, `t` type, `n` name), or
    None when it is forged, mangled or expired."""
    payload, _, mac = token.partition(".")
    if not payload or not mac or len(token) > 4096:
        return None
    expected = _b64(hmac.new(_key(), payload.encode(), hashlib.sha256).digest()[:18])
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        claim = json.loads(_unb64(payload))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(claim, dict) or not isinstance(claim.get("p"), str) or claim.get("m") not in ("image", "doc"):
        return None
    if not isinstance(claim.get("e"), int) or claim["e"] < (time.time() if now is None else now):
        return None
    if not claim["p"].startswith("s3://") or not isinstance(claim.get("t"), str):
        return None
    return claim


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
    thumb = await asyncio.to_thread(pdf_thumbnail, data) if mime == PDF else None
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
