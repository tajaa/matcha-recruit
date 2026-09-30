"""One-time OAuth `state` handles backed by Redis.

A system-browser OAuth callback carries no Matcha bearer token, so the
connect route stores an opaque 256-bit handle -> user id binding and the
callback consumes it exactly once (GETDEL). Both sides fail closed while
Redis is unavailable.

Same mechanism as the Gmail connect flow in routes/matcha_work/workspace.py
(which keeps its own copy, patched by name in its tests); new providers use
this module with their own key prefix so handles never cross providers.

`binding` ties a handle to the browser that started the flow: the connect
route sets a random nonce in an HttpOnly cookie and passes its hash here, and
the callback must present the same nonce. Without it, a person who opens
someone else's auth URL would connect THEIR account to the sender. Gmail
can't use it: the macOS app opens Gmail sign-in in the system browser, which
never saw the connect response's cookie.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from uuid import UUID

from app.core.services.redis_cache import get_redis_cache

STATE_TTL_SECONDS = 30 * 60
_STATE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class OAuthStateUnavailable(RuntimeError):
    """A secure, one-time OAuth state could not be issued or consumed."""


def _key(prefix: str, state: str) -> str:
    return f"{prefix}:{state}"


def binding_hash(nonce: str) -> str:
    return hashlib.sha256((nonce or "").encode()).hexdigest()


async def issue_state(prefix: str, user_id: UUID, ttl_seconds: int = STATE_TTL_SECONDS,
                      *, binding: str | None = None) -> str:
    redis = get_redis_cache()
    if redis is None:
        raise OAuthStateUnavailable("OAuth state store is unavailable")
    # SET NX never replaces a still-live handle on the (practically
    # impossible) random collision.
    for _attempt in range(3):
        state = secrets.token_urlsafe(32)
        try:
            value = f"{user_id}|{binding}" if binding else str(user_id)
            stored = await redis.set(_key(prefix, state), value, ex=ttl_seconds, nx=True)
        except Exception as exc:
            raise OAuthStateUnavailable("OAuth state store is unavailable") from exc
        if stored:
            return state
    raise OAuthStateUnavailable("Failed to allocate OAuth state")


async def consume_state(prefix: str, state: str, *, binding: str | None = None) -> UUID:
    """Atomically consume `state`; returns the initiating user. ValueError on
    an unknown, expired, replayed or malformed handle, or when the handle was
    issued with a binding and `binding` doesn't match it (consumed either way,
    so a wrong guess can't be retried)."""
    if not _STATE_PATTERN.fullmatch(state or ""):
        raise ValueError("Invalid or expired OAuth state")
    redis = get_redis_cache()
    if redis is None:
        raise OAuthStateUnavailable("OAuth state store is unavailable")
    try:
        user_id = await redis.getdel(_key(prefix, state))
    except Exception as exc:
        raise OAuthStateUnavailable("OAuth state store is unavailable") from exc
    if user_id is None:
        raise ValueError("Invalid or expired OAuth state")
    try:
        raw = user_id.decode() if isinstance(user_id, bytes) else user_id
        owner, _, bound = raw.partition("|")
        if bound and not (binding and hmac.compare_digest(bound, binding)):
            raise ValueError("OAuth state was started in another browser")
        return UUID(owner)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Invalid or expired OAuth state") from exc
