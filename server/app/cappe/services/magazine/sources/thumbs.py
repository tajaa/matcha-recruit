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

import base64
import hashlib
import hmac
import io
import json
import time
from typing import Optional

from PIL import Image

from .....config import get_settings

TTL_SECONDS = 6 * 3600
THUMB_SIDE = 480
MAX_SOURCE_BYTES = 4 * 1024 * 1024
PATH = "/public/stock-thumbs/"


def _key() -> bytes:
    return hashlib.sha256(b"cappe-stock-thumb:" + get_settings().jwt_secret_key.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(url: str, *, now: Optional[float] = None) -> str:
    payload = _b64(json.dumps({"u": url, "e": int((now or time.time()) + TTL_SECONDS)}, separators=(",", ":")).encode())
    mac = _b64(hmac.new(_key(), payload.encode(), hashlib.sha256).digest()[:18])
    return f"{payload}.{mac}"


def thumb_path(url: str) -> str:
    return PATH + sign(url) if url else ""


def verify(token: str, *, now: Optional[float] = None) -> Optional[str]:
    """The thumbnail URL a token stands for, or None (forged, mangled, expired)."""
    payload, _, mac = token.partition(".")
    if not payload or not mac or len(token) > 2048:
        return None
    expected = _b64(hmac.new(_key(), payload.encode(), hashlib.sha256).digest()[:18])
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("u"), str) or int(data.get("e", 0)) < (now or time.time()):
        return None
    return data["u"] if data["u"].startswith("https://") else None


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
