"""Rehost a result's product photos on our own CDN.

Clients never load a retailer's image URL directly: that would leak the
viewer's IP to arbitrary hosts, break on hotlink protection, and render
whatever bytes the host decides to serve later. Each image is fetched once
through the SSRF guard, decoded and re-encoded by Pillow (which also strips
metadata and refuses anything that is not really an image), and uploaded.
An image that fails any step is dropped, never shown raw.
"""
from __future__ import annotations

import asyncio
import io
import logging
from uuid import UUID

from PIL import Image

from app.core.services.safe_fetch import UnsafeURL, fetch_public
from app.core.services.storage import get_storage

logger = logging.getLogger(__name__)

MAX_IMAGES_PER_RUN = 6
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1200
_MAX_PIXELS = 40_000_000


def _reencode(data: bytes) -> bytes:
    """Decode, bound, and re-encode as WebP. Raises on anything not an image."""
    with Image.open(io.BytesIO(data)) as probe:
        probe.verify()
    with Image.open(io.BytesIO(data)) as img:
        if img.width * img.height > _MAX_PIXELS:
            raise ValueError("Image too large")
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=82, method=4)
        return out.getvalue()


async def _rehost_one(source_url: str, prefix: str) -> str | None:
    try:
        fetched = await fetch_public(source_url, max_bytes=MAX_IMAGE_BYTES, accept="image/*")
    except (UnsafeURL, Exception) as exc:  # network errors are just "no image"
        logger.info("agent card image fetch refused/failed: %s", exc)
        return None
    if fetched.status != 200 or fetched.truncated or not fetched.content_type.startswith("image/"):
        return None
    try:
        webp = await asyncio.to_thread(_reencode, fetched.body)
    except Exception:
        return None
    url = await get_storage().upload_file(webp, "photo.webp", prefix=prefix, content_type="image/webp")
    # Local-storage dev fallback returns a path, not a URL a client can load.
    return url if isinstance(url, str) and url.startswith("https://") else None


async def rehost_images(
    result: dict, *, company_id: UUID, project_id: UUID, task_id: UUID,
) -> list[str]:
    """Replace every pick's `images[].source_url` with a CDN `url`, in place.

    Returns warnings for images that were dropped.
    """
    prefix = f"matcha-work/{company_id}/{project_id}/agent/{task_id}"
    picks = [p for p in [result.get("top_pick"), *(result.get("alternatives") or [])] if p]
    budget = MAX_IMAGES_PER_RUN
    warnings: list[str] = []
    for pick in picks:
        kept = []
        for image in pick.get("images") or []:
            if budget <= 0:
                break
            budget -= 1
            url = await _rehost_one(image["source_url"], prefix)
            if url:
                kept.append({"url": url, "page_url": image["page_url"], "alt": image.get("alt") or pick["name"]})
            else:
                warnings.append(f"Dropped an image for {pick['name']}: could not load it safely")
        pick["images"] = kept
    return warnings
