"""Images the user attaches to a Merlin message.

Three uses, all from the same upload and all inferred from what the user says
rather than a mode switch:

  1. **Place it** — "use this as the hero image" → Merlin emits a `set_field`
     with the URL.
  2. **Style reference** — a screenshot or moodboard → "make my page look like
     this" → the pixels drive design ops.
  3. **Generation input** — "make a version of this with a lighter background"
     → the bytes are fed to the image model alongside the prompt.

Attachments arrive as URLs, not bytes: the panel uploads through the existing
`POST /sites/{id}/upload` (5MB raster, already virus-of-a-shape checked and
SVG-refused) and sends back what it got. That means this module MUST NOT fetch
whatever URL it is handed.

`storage.download_file` accepts any `https://*.cloudfront.net/...` over plain
HTTP and falls through to reading local file PATHS — handed a model- or
user-supplied string, that is an SSRF and a local-file read. `_is_own_storage`
is the gate: only URLs this deployment's own storage would have minted get
through, and everything else is dropped with a note rather than fetched.
"""
import io
import logging
from typing import Any, Optional

from ...config import get_settings
from ...core.services.storage import get_storage

logger = logging.getLogger(__name__)

# Per-turn cap. Each image is a real chunk of the context window, and the model
# cannot meaningfully hold more than a few references at once.
MAX_ATTACHMENTS = 4
# Refuse anything bigger than the upload route would have accepted.
MAX_BYTES = 5 * 1024 * 1024
# Long edge, in pixels. Beyond this an attachment costs tokens without adding
# detail the model uses — a moodboard reads the same at 1280px.
MAX_EDGE = 1280

ALLOWED_MIMES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})


def _is_own_storage(url: str) -> bool:
    """True only for URLs this deployment's storage produced.

    Deliberately narrow: an allowlist of our own CloudFront domain and our own
    bucket, not a generic "looks like a CDN" test. `.cloudfront.net` in general
    is attacker-registerable, and `download_file` would happily fetch it.
    """
    if not isinstance(url, str) or not url:
        return False
    settings = get_settings()
    domain = getattr(settings, "cloudfront_domain", None)
    bucket = getattr(settings, "s3_bucket", None)
    if domain and url.startswith(f"https://{domain}/"):
        return True
    if bucket and url.startswith(f"s3://{bucket}/"):
        return True
    return False


def _downscale(data: bytes) -> bytes:
    """Shrink to MAX_EDGE if larger. Returns the original on any failure — a
    resize is a cost optimization, never a correctness requirement."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            if max(img.size) <= MAX_EDGE:
                return data
            img = img.convert("RGB") if img.mode in ("P", "RGBA", "LA") else img
            img.thumbnail((MAX_EDGE, MAX_EDGE))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except Exception as exc:  # noqa: BLE001 — Pillow missing, animated gif, corrupt file
        logger.info("Merlin attachment downscale skipped: %s", exc)
        return data


async def load_attachments(raw: Any) -> list[dict[str, Any]]:
    """`[{url, mime}]` → `[{url, mime, data}]` for the ones we could fetch.

    Never raises. An attachment that fails the allowlist, the size cap or the
    fetch is dropped — the turn proceeds with the text, which is strictly better
    than 500ing on a stale URL.
    """
    if not isinstance(raw, list):
        return []
    storage = get_storage()
    out: list[dict[str, Any]] = []

    for item in raw[:MAX_ATTACHMENTS]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not _is_own_storage(url):
            logger.info("Merlin attachment refused (not our storage): %r", url)
            continue
        try:
            data = await storage.download_file(url)
        except Exception as exc:  # noqa: BLE001
            logger.info("Merlin attachment fetch failed: %s", exc)
            continue
        if not data or len(data) > MAX_BYTES:
            continue
        mime = item.get("mime") if item.get("mime") in ALLOWED_MIMES else "image/png"
        data = _downscale(data)
        # A downscale re-encodes to JPEG; the declared mime has to follow or the
        # model is handed a PNG label over JPEG bytes.
        if data is not None and data[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        out.append({"url": url, "mime": mime, "data": data})

    return out


def caption_lines(attachments: list[dict[str, Any]]) -> Optional[str]:
    """How the prompt refers to the attached images.

    The numbering is load-bearing: it's how the model names one in a
    `generate_image(attachment_index=...)` call, and how a "use this photo"
    request resolves to a URL it can put in a `set_field`.
    """
    if not attachments:
        return None
    lines = [
        "The user attached the following image(s), in order. They may want one "
        "PLACED on the page (use its URL as an image field's value), used as a "
        "STYLE REFERENCE (match its look with design ops), or used as INPUT to "
        "image generation. Decide from what they asked.",
    ]
    for i, att in enumerate(attachments):
        lines.append(f"Attachment {i + 1}: {att['url']}")
    return "\n".join(lines)
