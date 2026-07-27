"""Image attachment fetch for the multimodal prompt path: the SSRF-guarded URL
trust check, a size-capped download, and the batch prefetch the route runs
before handing messages to the (thread-pool) prompt builder.
"""
import asyncio
import logging
from typing import Optional
from app.config import get_settings
from cachetools import TTLCache  # noqa: E402

logger = logging.getLogger(__name__)


_IMAGE_FETCH_TIMEOUT = 10


_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB per image — keeps Gemini request sane


_EXT_MIME = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "webp": "image/webp", "heic": "image/heic",
    "bmp": "image/bmp", "tiff": "image/tiff",
}


def _is_trusted_image_url(url: str) -> bool:
    """Allow only our own CDN or local uploads. Prevents SSRF since the URL
    arrives from the client in the send request."""
    from urllib.parse import urlparse
    from app.config import get_settings

    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    cloudfront = (get_settings().cloudfront_domain or "").lower()
    if cloudfront and host == cloudfront:
        return True
    # Dev/local: allow the uploads endpoint proxied from the same origin.
    # Production should always route through CloudFront.
    if host in ("localhost", "127.0.0.1") and parsed.path.startswith("/uploads/"):
        return True
    return False


def _fetch_image_bytes(url: str) -> Optional[tuple[bytes, str]]:
    """Download an image URL and return (bytes, mime_type), or None on failure.
    Synchronous — call from asyncio.to_thread."""
    from urllib.request import Request, urlopen
    from urllib.parse import urlparse

    if not _is_trusted_image_url(url):
        logger.warning("Refusing to fetch untrusted image URL: %s", url)
        return None

    try:
        ext = urlparse(url).path.rsplit(".", 1)[-1].lower() if "." in urlparse(url).path else ""
        mime = _EXT_MIME.get(ext, "image/jpeg")
        req = Request(url, headers={"User-Agent": "matcha-work-ai/1.0"})
        with urlopen(req, timeout=_IMAGE_FETCH_TIMEOUT) as resp:
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            if content_type.startswith("image/"):
                mime = content_type
            data = resp.read(_MAX_IMAGE_BYTES + 1)
        if len(data) > _MAX_IMAGE_BYTES:
            logger.warning("Image exceeds %s byte limit: %s", _MAX_IMAGE_BYTES, url)
            return None
        return data, mime
    except Exception as e:
        logger.warning("Failed to fetch image %s: %s", url, e)
        return None


async def fetch_image_parts_for_messages(msg_dicts: list[dict]) -> None:
    """Populate msg['image_parts'] as [(bytes, mime), ...] by fetching any
    image_urls concurrently in a thread pool. Mutates msg_dicts in place."""
    fetches: list[tuple[dict, str]] = []
    for msg in msg_dicts:
        for url in (msg.get("image_urls") or []):
            if isinstance(url, str) and url:
                fetches.append((msg, url))
    if not fetches:
        return
    results = await asyncio.gather(
        *(asyncio.to_thread(_fetch_image_bytes, url) for _, url in fetches)
    )
    for (msg, _url), result in zip(fetches, results):
        if result is None:
            continue
        msg.setdefault("image_parts", []).append(result)
