"""The `state` a Connect round-trip carries, and the browser it belongs to.

The callback is a browser redirect with no bearer token, so the state is what
ties the code Meta hands back to the site and account that started the
connect. It is HMAC-signed with the server's JWT secret and expires, so a
state can't be forged to attach someone's Pages to another account, nor
replayed a day later.

Signing alone still lets an owner start a connect and send the Facebook link
to someone else, whose Pages would then land on the sender's site. So the
state also carries a nonce that the start response sets as an HttpOnly cookie
(`NONCE_COOKIE`); the callback accepts the state only from the browser that
holds the matching cookie.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Optional
from uuid import UUID

from app.config import get_settings

STATE_TTL_SECONDS = 15 * 60
NONCE_COOKIE = "cz_social_oauth"
# Scoped to the callback, so no other request ever carries it.
NONCE_COOKIE_PATH = "/api/cappe/public/social/meta"


def _seed() -> str:
    try:
        return get_settings().jwt_secret_key
    except RuntimeError:
        return os.getenv("JWT_SECRET_KEY") or "matcha-dev-secret"


def _sign(payload: bytes, seed: str) -> str:
    key = hashlib.sha256(f"cappe-social-oauth:{seed}".encode("utf-8")).digest()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()[:32]


def new_nonce() -> str:
    return secrets.token_urlsafe(18)


def make_state(
    site_id: UUID, account_id: UUID, nonce: str, *, now: Optional[float] = None, seed: Optional[str] = None,
) -> str:
    body = {
        "s": str(site_id), "a": str(account_id), "n": nonce,
        "exp": int((now if now is not None else time.time()) + STATE_TTL_SECONDS),
    }
    payload = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{payload}.{_sign(payload.encode('ascii'), seed or _seed())}"


def read_state(
    state: Optional[str], *, nonce_cookie: Optional[str], now: Optional[float] = None, seed: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """`{"site_id": UUID, "account_id": UUID}` for a state this server signed,
    that hasn't expired, and whose nonce matches the cookie this browser
    holds; None for anything else."""
    if not state or "." not in state or not nonce_cookie:
        return None
    payload, _, signature = state.rpartition(".")
    if not hmac.compare_digest(signature, _sign(payload.encode("ascii"), seed or _seed())):
        return None
    try:
        padded = payload + "=" * (-len(payload) % 4)
        body = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        site_id, account_id, exp, nonce = UUID(body["s"]), UUID(body["a"]), int(body["exp"]), str(body["n"])
    except (ValueError, KeyError, TypeError):
        return None
    if exp < (now if now is not None else time.time()):
        return None
    if not hmac.compare_digest(nonce, nonce_cookie):
        return None
    return {"site_id": site_id, "account_id": account_id}


__all__ = ["STATE_TTL_SECONDS", "NONCE_COOKIE", "NONCE_COOKIE_PATH", "new_nonce", "make_state", "read_state"]
