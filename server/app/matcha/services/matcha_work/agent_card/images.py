"""Rehost a result's product photos on our own CDN.

Clients never load a retailer's image URL directly: that would leak the
viewer's IP to arbitrary hosts, break on hotlink protection, and render
whatever bytes the host decides to serve later. Each image is fetched once
through the SSRF guard, decoded and re-encoded by Pillow (which also strips
metadata and refuses anything that is not really an image), and uploaded.
An image that fails any step is dropped, never shown raw — and a failed photo
never fails the run.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from uuid import UUID

from PIL import Image

from app.core.services.safe_fetch import fetch_public
from app.core.services.storage import get_storage

logger = logging.getLogger(__name__)

MAX_IMAGES_PER_RUN = 6
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1200
_MAX_PIXELS = 40_000_000
_PER_IMAGE_SECONDS = 20.0


class StorageHasNoPublicUrl(RuntimeError):
    """Uploads succeed but return something a browser can't load (an `s3://`
    URI or a local path) — CLOUDFRONT_DOMAIN unset. No image can be shown."""


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
    """A CDN URL for the image, or None if it can't be fetched/decoded/stored.

    Raises StorageHasNoPublicUrl when storage isn't configured to hand out
    loadable URLs — that is a deployment problem, not a bad image."""
    try:
        fetched = await fetch_public(
            source_url, max_bytes=MAX_IMAGE_BYTES, accept="image/*",
            total_timeout=_PER_IMAGE_SECONDS,
        )
    except Exception as exc:  # unsafe host, network error, timeout: just no image
        logger.info("agent card image fetch refused/failed: %s", exc)
        return None
    if fetched.status != 200 or fetched.truncated or not fetched.content_type.startswith("image/"):
        return None
    try:
        webp = await asyncio.to_thread(_reencode, fetched.body)
    except Exception:
        return None
    try:
        url = await asyncio.wait_for(
            get_storage().upload_file(webp, "photo.webp", prefix=prefix, content_type="image/webp"),
            timeout=_PER_IMAGE_SECONDS,
        )
    except Exception:
        # An S3 hiccup costs this photo, not the whole run.
        logger.warning("agent card image upload failed", exc_info=True)
        return None
    if not (isinstance(url, str) and url.startswith("https://")):
        raise StorageHasNoPublicUrl(str(url)[:40])
    return url


async def rehost_images(
    result: dict, *, company_id: UUID, project_id: UUID, task_id: UUID,
    total_seconds: float = 60.0,
) -> list[str]:
    """Replace every pick's `images[].source_url` with a CDN `url`, in place.

    Every pick ends up with only fully rehosted images, however this ends:
    out of budget, out of time, or storage unable to serve URLs. Returns
    warnings for what was dropped.
    """
    prefix = f"matcha-work/{company_id}/{project_id}/agent/{task_id}"
    picks = [p for p in [result.get("top_pick"), *(result.get("alternatives") or [])] if p]
    deadline = time.monotonic() + total_seconds
    budget = MAX_IMAGES_PER_RUN
    storage_ok = True
    warnings: list[str] = []
    for pick in picks:
        kept = []
        for image in pick.get("images") or []:
            remaining = deadline - time.monotonic()
            if budget <= 0 or remaining <= 1 or not storage_ok:
                continue
            budget -= 1
            try:
                url = await asyncio.wait_for(
                    _rehost_one(image["source_url"], prefix),
                    timeout=min(_PER_IMAGE_SECONDS * 2, remaining),
                )
            except StorageHasNoPublicUrl:
                storage_ok = False
                logger.warning("agent card photos dropped: storage returns no public URL (CLOUDFRONT_DOMAIN unset?)")
                warnings.append("Photos are unavailable: image storage has no public URL configured")
                continue
            except TimeoutError:
                url = None
            if url:
                kept.append({"url": url, "page_url": image["page_url"], "alt": image.get("alt") or pick["name"]})
            else:
                warnings.append(f"Dropped an image for {pick['name']}: could not load it safely")
        pick["images"] = kept
    return warnings
