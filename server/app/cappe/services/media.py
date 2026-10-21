"""Image processing for every Cappe image upload and the magazine library.

Uploads used to be stored byte-for-byte, so a phone photo kept its EXIF —
camera serial, time, and the GPS position of wherever it was taken — on a
public CDN URL. Everything that stores an image now goes through
`process_image`, which decodes it, turns it the right way up, and writes a new
file from the pixels alone, so no metadata can ride along.

For the magazine library it also makes the responsive sizes a story page
needs: WebP at `VARIANT_WIDTHS` (never wider than the original) for `srcset`,
and one JPEG at `SHARE_WIDTH` for email and link previews, where WebP is still
handled badly.

Pure Pillow, CPU-bound: callers run `process_image` in `asyncio.to_thread`.
`store_processed` uploads the result through the shared storage service.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from PIL import Image, ImageOps, ImageSequence

from ...core.services.storage import get_storage

logger = logging.getLogger(__name__)

# A 50 MP photo is already larger than any phone shoots; past that it is a
# decompression bomb, not a picture.
MAX_PIXELS = 50_000_000
# The stored copy is capped here: a story column is at most ~2000 px wide on a
# retina screen, and this keeps an 8K upload from becoming an 8K page image.
MAX_SIDE = 3200
VARIANT_WIDTHS = (480, 960, 1440, 2048)
SHARE_WIDTH = 1200

_JPEG_QUALITY = 88
_WEBP_QUALITY = 80

_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}


class ImageRejected(ValueError):
    """The bytes are not an image we will store (undecodable or too large)."""


@dataclass(frozen=True)
class Variant:
    width: int
    data: bytes
    mime: str


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    mime: str
    width: int
    height: int
    webp: tuple[Variant, ...] = ()
    share: Optional[Variant] = None

    @property
    def ext(self) -> str:
        return _EXT[self.mime]


@dataclass(frozen=True)
class StoredImage:
    url: str
    mime: str
    width: int
    height: int
    bytes: int
    variants: dict[str, Any] = field(default_factory=dict)


def _open(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        img = Image.open(io.BytesIO(data))
    except Exception as exc:  # Pillow raises a different error per format
        raise ImageRejected("That file isn't an image we can read.") from exc
    if img.width * img.height > MAX_PIXELS:
        raise ImageRejected("That image is too large.")
    return img


def _to_srgb(img: Image.Image) -> Image.Image:
    """Convert an image with an embedded colour profile (a phone's Display P3)
    to sRGB, so dropping the profile doesn't shift its colours. Best effort:
    an unreadable profile leaves the pixels as they are."""
    icc = img.info.get("icc_profile")
    if not icc or img.mode not in ("RGB", "RGBA"):
        return img
    try:
        from PIL import ImageCms

        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        dst = ImageCms.createProfile("sRGB")
        converted = ImageCms.profileToProfile(img, src, dst, outputMode=img.mode)
        return converted or img
    except Exception:  # noqa: BLE001 — colour fidelity is not worth failing an upload
        return img


def _clean(img: Image.Image) -> Image.Image:
    """The pixels alone, upright, in RGB or RGBA: a new image object, so no
    EXIF, XMP, comment or profile from the original can be written back."""
    img = ImageOps.exif_transpose(img)
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA" if has_alpha else "RGB")
    img = _to_srgb(img)
    return Image.frombytes(img.mode, img.size, img.tobytes())


def _encode(img: Image.Image, fmt: str, **params) -> bytes:
    out = io.BytesIO()
    img.save(out, format=fmt, **params)
    return out.getvalue()


def _flatten(img: Image.Image) -> Image.Image:
    if img.mode != "RGBA":
        return img
    base = Image.new("RGB", img.size, "white")
    base.paste(img, mask=img.getchannel("A"))
    return base


def _resized(img: Image.Image, width: int) -> Image.Image:
    if width >= img.width:
        return img
    height = max(1, round(img.height * width / img.width))
    return img.resize((width, height), Image.LANCZOS)


def _animated(img: Image.Image, data: bytes, mime: str) -> ProcessedImage:
    """GIF carries no EXIF and is stored as it came. An animated WebP can, so
    its frames are written again without it."""
    if mime == "image/gif":
        return ProcessedImage(data=data, mime=mime, width=img.width, height=img.height)
    frames, durations = [], []
    for frame in ImageSequence.Iterator(img):
        frames.append(Image.frombytes("RGBA", frame.size, frame.convert("RGBA").tobytes()))
        durations.append(frame.info.get("duration", 100))
    out = _encode(frames[0], "WEBP", save_all=True, append_images=frames[1:], duration=durations,
                  loop=img.info.get("loop", 0), quality=_WEBP_QUALITY)
    return ProcessedImage(data=out, mime=mime, width=img.width, height=img.height)


def variant_widths(width: int) -> tuple[int, ...]:
    """The srcset widths for an image `width` px wide: every standard width
    below it, plus the image's own width when it is narrower than the largest
    (so a 1000 px photo gets 480, 960 and 1000, never an upscaled 1440)."""
    widths = [w for w in VARIANT_WIDTHS if w < width]
    top = min(width, VARIANT_WIDTHS[-1])
    if top not in widths:
        widths.append(top)
    return tuple(widths)


def process_image(data: bytes, mime: str, *, derivatives: bool = False) -> ProcessedImage:
    """Re-encode an uploaded image without its metadata, and optionally make
    its responsive sizes. Raises `ImageRejected`."""
    img = _open(data)
    if getattr(img, "is_animated", False):
        return _animated(img, data, mime)

    clean = _clean(img)
    if max(clean.size) > MAX_SIDE:
        clean.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)

    if mime == "image/jpeg":
        main, out_mime = _encode(_flatten(clean), "JPEG", quality=_JPEG_QUALITY, optimize=True,
                                 progressive=True), "image/jpeg"
    elif mime == "image/webp":
        main, out_mime = _encode(clean, "WEBP", quality=_JPEG_QUALITY, method=4), "image/webp"
    else:  # PNG, and a still GIF (a one-frame GIF is better as PNG)
        main, out_mime = _encode(clean, "PNG", optimize=True), "image/png"

    if not derivatives:
        return ProcessedImage(data=main, mime=out_mime, width=clean.width, height=clean.height)

    webp = tuple(
        Variant(w, _encode(_resized(clean, w), "WEBP", quality=_WEBP_QUALITY, method=4), "image/webp")
        for w in variant_widths(clean.width)
    )
    share_img = _flatten(_resized(clean, SHARE_WIDTH))
    share = Variant(share_img.width, _encode(share_img, "JPEG", quality=85, optimize=True), "image/jpeg")
    return ProcessedImage(data=main, mime=out_mime, width=clean.width, height=clean.height,
                          webp=webp, share=share)


def filename_for(original: Optional[str], ext: str) -> str:
    """The upload's own name with the extension of what we actually store."""
    stem = os.path.splitext(os.path.basename(original or ""))[0] or "image"
    return f"{stem}{ext}"


async def store_processed(image: ProcessedImage, *, prefix: str, filename: Optional[str] = None,
                          main_url: Optional[str] = None) -> StoredImage:
    """Upload the image and its sizes. The sizes go up in parallel; any upload
    failure raises (the caller decides whether that fails the request).

    `main_url`: the original is already stored there (an AI illustration keeps
    the file the generator made, with its own provenance data), so only the
    sizes are uploaded."""
    storage = get_storage()
    sizes = [storage.upload_file(file_bytes=v.data, filename=f"w{v.width}.webp", prefix=prefix,
                                 content_type=v.mime) for v in image.webp]
    if image.share:
        sizes.append(storage.upload_file(file_bytes=image.share.data, filename="share.jpg", prefix=prefix,
                                         content_type=image.share.mime))
    if main_url:
        urls = [main_url, *await asyncio.gather(*sizes)]
    else:
        urls = await asyncio.gather(
            storage.upload_file(file_bytes=image.data, filename=filename_for(filename, image.ext), prefix=prefix,
                                content_type=image.mime),
            *sizes,
        )
    variants: dict[str, Any] = {}
    if image.webp:
        variants["webp"] = [{"w": v.width, "url": url} for v, url in zip(image.webp, urls[1:])]
    if image.share:
        variants["share"] = {"w": image.share.width, "url": urls[-1]}
    return StoredImage(url=urls[0], mime=image.mime, width=image.width, height=image.height,
                       bytes=len(image.data), variants=variants)
