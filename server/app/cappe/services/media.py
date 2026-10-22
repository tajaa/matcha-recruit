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
# An animation is decoded frame by frame into memory (RGBA, 4 bytes a pixel),
# so its frames together get a budget of their own.
MAX_ANIMATED_PIXELS = 40_000_000
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


def _to_srgb(img: Image.Image, mode: str) -> Optional[Image.Image]:
    """`img` in sRGB and `mode`, through its embedded colour profile (a phone's
    Display P3, a press photo's CMYK), so dropping the profile doesn't shift
    its colours. The profile describes the pixels as they came, so it is
    applied before any other conversion. None when there is no profile or it
    can't be read: the caller converts naively."""
    icc = img.info.get("icc_profile")
    if not icc or img.mode not in ("RGB", "RGBA", "CMYK"):
        return None
    try:
        from PIL import ImageCms

        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        dst = ImageCms.createProfile("sRGB")
        return ImageCms.profileToProfile(img, src, dst, outputMode=mode)
    except Exception:  # noqa: BLE001 — colour fidelity is not worth failing an upload
        return None


def _clean(img: Image.Image) -> Image.Image:
    """The pixels alone, upright, in RGB or RGBA: a new image object, so no
    EXIF, XMP, comment or profile from the original can be written back."""
    img = ImageOps.exif_transpose(img)
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    mode = "RGBA" if has_alpha else "RGB"
    img = _to_srgb(img, mode) or img.convert(mode)
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


# GIF extensions an animation needs: how a frame is shown and how it loops.
_GIF_KEEP_APPS = (b"NETSCAPE2.0", b"ANIMEXTS1.0")


def _gif_without_metadata(data: bytes) -> bytes:
    """The GIF's own bytes, losslessly, minus everything that isn't picture:
    comment and plain-text extensions, application extensions other than
    looping (XMP rides in one, and can carry a GPS position), and anything
    after the trailer. Re-encoding would re-quantize every frame."""
    def sub_blocks(i: int) -> int:
        while True:
            size = data[i]
            i += 1 + size
            if size == 0:
                return i

    try:
        if data[:6] not in (b"GIF87a", b"GIF89a"):
            raise ValueError("not a GIF")
        packed = data[10]
        i = 13 + (3 * (2 << (packed & 7)) if packed & 0x80 else 0)
        out = [data[:i]]
        while True:
            kind = data[i]
            if kind == 0x3B:  # trailer
                out.append(b"\x3b")
                return b"".join(out)
            if kind == 0x2C:  # an image: descriptor, local colour table, LZW data
                packed = data[i + 9]
                j = i + 10 + (3 * (2 << (packed & 7)) if packed & 0x80 else 0) + 1
                end = sub_blocks(j)
                out.append(data[i:end])
            elif kind == 0x21:
                label = data[i + 1]
                end = sub_blocks(i + 2)
                app = data[i + 3:i + 3 + data[i + 2]] if label == 0xFF else b""
                if label == 0xF9 or app in _GIF_KEEP_APPS:
                    out.append(data[i:end])
            else:
                raise ValueError(f"unknown GIF block {kind:#x}")
            if end > len(data):
                raise ValueError("truncated")
            i = end
    except (IndexError, ValueError) as exc:
        raise ImageRejected("That file isn't an image we can read.") from exc


def _animated(img: Image.Image, data: bytes, mime: str) -> ProcessedImage:
    """A GIF keeps its frames as they came, with its metadata cut out. Any
    other animation (WebP, APNG) has its frames written again as WebP."""
    if mime == "image/gif":
        return ProcessedImage(data=_gif_without_metadata(data), mime=mime, width=img.width, height=img.height)
    if img.width * img.height * getattr(img, "n_frames", 1) > MAX_ANIMATED_PIXELS:
        raise ImageRejected("That animation is too large.")
    frames, durations = [], []
    for frame in ImageSequence.Iterator(img):
        frames.append(Image.frombytes("RGBA", frame.size, frame.convert("RGBA").tobytes()))
        durations.append(frame.info.get("duration", 100))
    out = _encode(frames[0], "WEBP", save_all=True, append_images=frames[1:], duration=durations,
                  loop=img.info.get("loop", 0), quality=_WEBP_QUALITY)
    return ProcessedImage(data=out, mime="image/webp", width=img.width, height=img.height)


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


async def store_processed(image: ProcessedImage, *, prefix: str, filename: Optional[str] = None) -> StoredImage:
    """Upload the image and its sizes. The sizes go up in parallel; any upload
    failure raises (the caller decides whether that fails the request)."""
    storage = get_storage()
    main_name = filename_for(filename, image.ext)
    jobs = [storage.upload_file(file_bytes=image.data, filename=main_name, prefix=prefix,
                                content_type=image.mime)]
    jobs += [storage.upload_file(file_bytes=v.data, filename=f"w{v.width}.webp", prefix=prefix,
                                 content_type=v.mime) for v in image.webp]
    if image.share:
        jobs.append(storage.upload_file(file_bytes=image.share.data, filename="share.jpg", prefix=prefix,
                                        content_type=image.share.mime))
    urls = await asyncio.gather(*jobs)
    variants: dict[str, Any] = {}
    if image.webp:
        variants["webp"] = [{"w": v.width, "url": url} for v, url in zip(image.webp, urls[1:])]
    if image.share:
        variants["share"] = {"w": image.share.width, "url": urls[-1]}
    return StoredImage(url=urls[0], mime=image.mime, width=image.width, height=image.height,
                       bytes=len(image.data), variants=variants)
