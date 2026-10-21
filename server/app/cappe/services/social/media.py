"""Photos dropped into the composer, made postable everywhere.

Instagram's publishing API takes JPEG only, at most 1440 px wide, with an
aspect ratio between 4:5 and 1.91:1, and refuses anything else at publish
time — long after the owner walked away. So every social upload is
normalized here, up front: EXIF-rotated, flattened onto white, fitted inside
1440 px, and PADDED (never cropped: a product photo must not lose the
product) to the nearest allowed ratio, then saved as a JPEG under 8 MB.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from fastapi import HTTPException, status

MAX_EDGE = 1440
MIN_RATIO = 4 / 5        # tallest Instagram allows (portrait 4:5)
MAX_RATIO = 1.91         # widest (landscape 1.91:1)
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
PAD_COLOR = "white"


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    width: int
    height: int
    padded: bool


def target_canvas(width: int, height: int) -> tuple[int, int]:
    """The canvas an image of this size is padded onto: itself when its
    ratio is allowed, else widened (too tall) or heightened (too wide)."""
    ratio = width / height
    if ratio < MIN_RATIO:
        return round(height * MIN_RATIO), height
    if ratio > MAX_RATIO:
        return width, round(width / MAX_RATIO)
    return width, height


def prepare_image(data: bytes) -> PreparedImage:
    """Raises HTTPException(400) for anything Pillow can't decode."""
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data)) as source:
            source.seek(0)
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                flat = Image.new("RGB", rgba.size, PAD_COLOR)
                flat.paste(rgba, mask=rgba.getchannel("A"))
                image = flat
            elif image.mode != "RGB":
                image = image.convert("RGB")
            image.thumbnail((MAX_EDGE, MAX_EDGE))
            canvas_size = target_canvas(*image.size)
            padded = canvas_size != image.size
            if padded:
                canvas = Image.new("RGB", canvas_size, PAD_COLOR)
                canvas.paste(image, ((canvas_size[0] - image.width) // 2, (canvas_size[1] - image.height) // 2))
                image = canvas
            for quality in (88, 80, 70, 60):
                out = io.BytesIO()
                image.save(out, format="JPEG", quality=quality, optimize=True)
                if out.tell() <= MAX_OUTPUT_BYTES:
                    return PreparedImage(out.getvalue(), image.width, image.height, padded)
    except HTTPException:
        raise
    except Exception as exc:  # Pillow raises several format-specific errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That image couldn't be read. Try a JPG, PNG or WebP photo.",
        ) from exc
    raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="That photo is too detailed to post")


__all__ = ["MAX_EDGE", "MIN_RATIO", "MAX_RATIO", "PreparedImage", "target_canvas", "prepare_image"]
