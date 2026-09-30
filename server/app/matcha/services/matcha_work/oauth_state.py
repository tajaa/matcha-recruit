"""One-time OAuth `state` handles backed by Redis.

A system-browser OAuth callback carries no Matcha bearer token, so the
connect route stores an opaque 256-bit handle -> user id binding and the
callback consumes it exactly once (GETDEL). Both sides fail closed while
Redis is unavailable.

Same mechanism as the Gmail connect flow in routes/matcha_work/workspace.py
(which keeps its own copy, patched by name in its tests); new providers use
this module with their own key prefix so handles never cross providers.
"""

from __future__ import annotations

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


async def issue_state(prefix: str, user_id: UUID, ttl_seconds: int = STATE_TTL_SECONDS) -> str:
    redis = get_redis_cache()
    if redis is None:
        raise OAuthStateUnavailable("OAuth state store is unavailable")
    # SET NX never replaces a still-live handle on the (practically
    # impossible) random collision.
    for _attempt in range(3):
        state = secrets.token_urlsafe(32)
        try:
            stored = await redis.set(_key(prefix, state), str(user_id), ex=ttl_seconds, nx=True)
        except Exception as exc:
            raise OAuthStateUnavailable("OAuth state store is unavailable") from exc
        if stored:
            return state
    raise OAuthStateUnavailable("Failed to allocate OAuth state")


async def consume_state(prefix: str, state: str) -> UUID:
    """Atomically consume `state`; returns the initiating user. ValueError on
    an unknown, expired, replayed or malformed handle."""
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
        return UUID(user_id.decode() if isinstance(user_id, bytes) else user_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Invalid or expired OAuth state") from exc
