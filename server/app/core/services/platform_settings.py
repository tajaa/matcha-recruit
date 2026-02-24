"""Helpers for frequently-read platform settings."""

import json
import logging
import time
from typing import Sequence

from ...database import get_connection

logger = logging.getLogger(__name__)

DEFAULT_VISIBLE_FEATURES = [
    "offer_letters",
    "client_management",
    "blog",
    "policies",
    "handbooks",
    "er_copilot",
    "onboarding",
    "employees",
]
VISIBLE_FEATURES_CACHE_TTL_SECONDS = 30

_visible_features_cache: list[str] | None = None
_visible_features_cached_at: float = 0.0


def _normalize_visible_features(value: object) -> list[str]:
    if value is None:
        return list(DEFAULT_VISIBLE_FEATURES)

    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Invalid visible_features payload in platform_settings; using defaults")
            return list(DEFAULT_VISIBLE_FEATURES)

    if not isinstance(parsed, list):
        return list(DEFAULT_VISIBLE_FEATURES)

    normalized = [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
    return normalized if normalized else list(DEFAULT_VISIBLE_FEATURES)


def invalidate_visible_features_cache() -> None:
    global _visible_features_cache, _visible_features_cached_at
    _visible_features_cache = None
    _visible_features_cached_at = 0.0


def prime_visible_features_cache(features: Sequence[str]) -> list[str]:
    global _visible_features_cache, _visible_features_cached_at
    normalized = _normalize_visible_features(list(features))
    _visible_features_cache = normalized
    _visible_features_cached_at = time.monotonic()
    return list(normalized)


async def get_visible_features(*, conn=None) -> list[str]:
    global _visible_features_cache, _visible_features_cached_at

    now = time.monotonic()
    if (
        _visible_features_cache is not None
        and now - _visible_features_cached_at < VISIBLE_FEATURES_CACHE_TTL_SECONDS
    ):
        return list(_visible_features_cache)

    if conn is None:
        async with get_connection() as managed_conn:
            raw = await managed_conn.fetchval(
                "SELECT value FROM platform_settings WHERE key = 'visible_features'"
            )
    else:
        raw = await conn.fetchval(
            "SELECT value FROM platform_settings WHERE key = 'visible_features'"
        )

    normalized = _normalize_visible_features(raw)
    _visible_features_cache = normalized
    _visible_features_cached_at = now
    return list(normalized)
