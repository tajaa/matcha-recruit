"""Signed claims for links an `<img>` or a click can follow without the
dashboard's bearer token: archive thumbnails (`magazine/sources/thumbs.py`)
and mood-board files (`boards/files.py`).

A token is `<payload>.<mac>`: the claim as compact JSON in URL-safe base64,
and an HMAC-SHA256 of it (first 18 bytes) under a key derived from the app's
secret and the link's `purpose`, so a token minted for one kind of link is
never good for another. The payload is readable by anyone holding the link:
put in it only what may be read (an archive's public URL, a pin's id), never
a storage path. Every claim carries its expiry `e` (unix seconds).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from ...config import get_settings

MAX_TOKEN = 2048


def _key(purpose: bytes) -> bytes:
    return hashlib.sha256(purpose + b":" + get_settings().jwt_secret_key.encode()).digest()


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(purpose: bytes, claim: dict) -> str:
    payload = b64(json.dumps(claim, separators=(",", ":")).encode())
    mac = b64(hmac.new(_key(purpose), payload.encode(), hashlib.sha256).digest()[:18])
    return f"{payload}.{mac}"


def verify(purpose: bytes, token: str, *, now: Optional[float] = None) -> Optional[dict]:
    """The claim a token stands for, or None when it is forged, mangled,
    minted for another purpose, or past its expiry."""
    payload, _, mac = token.partition(".")
    if not payload or not mac or len(token) > MAX_TOKEN:
        return None
    expected = b64(hmac.new(_key(purpose), payload.encode(), hashlib.sha256).digest()[:18])
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        claim = json.loads(unb64(payload))
    except ValueError:  # bad base64 or JSON (UnicodeDecodeError is a ValueError)
        return None
    if not isinstance(claim, dict) or not isinstance(claim.get("e"), int) or isinstance(claim["e"], bool):
        return None
    if claim["e"] < (time.time() if now is None else now):
        return None
    return claim
