"""Signed links for archive thumbnails, served from our own origin.

The dashboard's CSP lets images load only from our origin and CloudFront, and
it should stay that way, so a search result's thumbnail is not the archive's
URL but `/public/stock-thumbs/<token>` under the Cappe API (the dashboard
prefixes its API base, as for every call). The token is the thumbnail
URL with an expiry, signed with the app's secret, so the endpoint fetches only
addresses a search of ours produced — it is not an open image proxy. The
image is fetched through the SSRF-guarded fetcher, re-encoded as a small WebP
(nothing of the original's bytes is passed on) and cached.
"""
from __future__ import annotations

import io
import time
from typing import Optional

from PIL import Image

from ... import signed_links

TTL_SECONDS = 6 * 3600
THUMB_SIDE = 480
MAX_SOURCE_BYTES = 4 * 1024 * 1024
PATH = "/public/stock-thumbs/"
PURPOSE = b"cappe-stock-thumb"
_b64 = signed_links.b64  # tests forge payloads with it


def sign(url: str, *, now: Optional[float] = None) -> str:
    return signed_links.sign(PURPOSE, {"u": url, "e": int((now or time.time()) + TTL_SECONDS)})


def thumb_path(url: str) -> str:
    return PATH + sign(url) if url else ""


def verify(token: str, *, now: Optional[float] = None) -> Optional[str]:
    """The thumbnail URL a token stands for, or None (forged, mangled, expired)."""
    claim = signed_links.verify(PURPOSE, token, now=now)
    if claim is None or not isinstance(claim.get("u"), str):
        return None
    return claim["u"] if claim["u"].startswith("https://") else None


def to_webp(data: bytes) -> bytes:
    """A small WebP of an image (raises on anything that isn't one)."""
    with Image.open(io.BytesIO(data)) as probe:
        probe.verify()
    with Image.open(io.BytesIO(data)) as img:
        if img.width * img.height > 40_000_000:
            raise ValueError("too large")
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
        img.thumbnail((THUMB_SIDE, THUMB_SIDE))
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=72, method=4)
        return out.getvalue()
