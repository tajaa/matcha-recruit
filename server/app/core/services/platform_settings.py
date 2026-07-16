"""Helpers for frequently-read platform settings."""

import json
import logging
import time
from typing import Sequence

# connection_or_direct, not get_connection: these settings are read on the way to
# EVERY Gemini call (get_jurisdiction_research_model_mode picks the model), so a
# hard pool requirement here — like the one in the rate limiter — meant no Celery
# task could call Gemini at all. Workers are pool-free by design (celery_app.py).
# The `conn=None` managed path is the one that needs it; callers that already hold
# a connection pass it and never reach this.
from ...database import connection_or_direct as get_connection

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
DEFAULT_MATCHA_WORK_MODEL_MODE = "light"
DEFAULT_JURISDICTION_RESEARCH_MODEL_MODE = "light"
VISIBLE_FEATURES_CACHE_TTL_SECONDS = 30

# Serve tenants ONLY requirements whose catalog row carries a verified statute
# citation. Defaults TRUE and is fail-closed everywhere below (an unreadable
# value gates rather than opens): a business reading our compliance tab must be
# able to say "these are the laws that apply to me" without qualification, and a
# Gemini-researched row we have not tied to a statute cannot carry that claim.
#
# The gate is READ-time only. `_sync_requirements_to_location` prunes — it
# deletes any per-location row a check run does not re-emit — so filtering the
# WRITE path would destroy the uncodified projections instead of hiding them,
# and turning the gate back off would show an empty tab until every location
# re-researched. Hidden, not deleted, is what makes this reversible.
DEFAULT_TENANT_CODIFIED_ONLY = True

_visible_features_cache: list[str] | None = None
_visible_features_cached_at: float = 0.0

_matcha_work_model_mode_cache: str | None = None
_matcha_work_model_mode_cached_at: float = 0.0

_jurisdiction_research_model_mode_cache: str | None = None
_jurisdiction_research_model_mode_cached_at: float = 0.0

_er_similarity_weights_cache: dict[str, float] | None = None
_er_similarity_weights_cached_at: float = 0.0

_tenant_codified_only_cache: bool | None = None
_tenant_codified_only_cached_at: float = 0.0

DEFAULT_ER_SIMILARITY_WEIGHTS = {
    "category": 0.30,
    "status": 0.05,
    "evidence": 0.10,
    "temporal": 0.05,
    "intake": 0.05,
    "text": 0.35,
    "investigation": 0.10,
}
EXPECTED_WEIGHT_KEYS = set(DEFAULT_ER_SIMILARITY_WEIGHTS.keys())


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


def prime_matcha_work_model_mode_cache(mode: str) -> str:
    global _matcha_work_model_mode_cache, _matcha_work_model_mode_cached_at
    _matcha_work_model_mode_cache = mode
    _matcha_work_model_mode_cached_at = time.monotonic()
    return mode


def prime_jurisdiction_research_model_mode_cache(mode: str) -> str:
    global _jurisdiction_research_model_mode_cache, _jurisdiction_research_model_mode_cached_at
    _jurisdiction_research_model_mode_cache = mode
    _jurisdiction_research_model_mode_cached_at = time.monotonic()
    return mode


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


async def get_matcha_work_model_mode(*, conn=None) -> str:
    global _matcha_work_model_mode_cache, _matcha_work_model_mode_cached_at

    now = time.monotonic()
    if (
        _matcha_work_model_mode_cache is not None
        and now - _matcha_work_model_mode_cached_at < VISIBLE_FEATURES_CACHE_TTL_SECONDS
    ):
        return _matcha_work_model_mode_cache

    if conn is None:
        async with get_connection() as managed_conn:
            raw = await managed_conn.fetchval(
                "SELECT value FROM platform_settings WHERE key = 'matcha_work_model_mode'"
            )
    else:
        raw = await conn.fetchval(
            "SELECT value FROM platform_settings WHERE key = 'matcha_work_model_mode'"
        )

    if raw is None:
        return DEFAULT_MATCHA_WORK_MODEL_MODE

    # Value is JSONB, so it might be quoted string or just string if it was inserted as such
    if isinstance(raw, str):
        try:
            mode = json.loads(raw)
        except json.JSONDecodeError:
            mode = raw
    else:
        mode = str(raw)

    if mode not in ["light", "heavy"]:
        mode = DEFAULT_MATCHA_WORK_MODEL_MODE

    _matcha_work_model_mode_cache = mode
    _matcha_work_model_mode_cached_at = now
    return mode


async def get_jurisdiction_research_model_mode(*, conn=None) -> str:
    global _jurisdiction_research_model_mode_cache, _jurisdiction_research_model_mode_cached_at

    now = time.monotonic()
    if (
        _jurisdiction_research_model_mode_cache is not None
        and now - _jurisdiction_research_model_mode_cached_at < VISIBLE_FEATURES_CACHE_TTL_SECONDS
    ):
        return _jurisdiction_research_model_mode_cache

    if conn is None:
        async with get_connection() as managed_conn:
            raw = await managed_conn.fetchval(
                "SELECT value FROM platform_settings WHERE key = 'jurisdiction_research_model_mode'"
            )
    else:
        raw = await conn.fetchval(
            "SELECT value FROM platform_settings WHERE key = 'jurisdiction_research_model_mode'"
        )

    if raw is None:
        return DEFAULT_JURISDICTION_RESEARCH_MODEL_MODE

    if isinstance(raw, str):
        try:
            mode = json.loads(raw)
        except json.JSONDecodeError:
            mode = raw
    else:
        mode = str(raw)

    if mode not in ["lite", "light", "heavy"]:
        mode = DEFAULT_JURISDICTION_RESEARCH_MODEL_MODE

    _jurisdiction_research_model_mode_cache = mode
    _jurisdiction_research_model_mode_cached_at = now
    return mode


def invalidate_tenant_codified_only_cache() -> None:
    global _tenant_codified_only_cache, _tenant_codified_only_cached_at
    _tenant_codified_only_cache = None
    _tenant_codified_only_cached_at = 0.0


def prime_tenant_codified_only_cache(enabled: bool) -> bool:
    global _tenant_codified_only_cache, _tenant_codified_only_cached_at
    _tenant_codified_only_cache = bool(enabled)
    _tenant_codified_only_cached_at = time.monotonic()
    return bool(enabled)


def _normalize_tenant_codified_only(value: object) -> bool:
    """Fail CLOSED. Every unreadable shape gates rather than opens.

    The failure modes are asymmetric: gating wrongly shows a business fewer
    laws than we hold, which is visible and complained about. Opening wrongly
    presents unvetted research as verified law, which looks exactly like the
    real thing — nobody reports it, and it is the whole reason the gate exists.
    """
    if value is None:
        return DEFAULT_TENANT_CODIFIED_ONLY

    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Invalid tenant_codified_only payload; keeping the gate ON")
            return True

    # Accepts {"enabled": bool} (the admin route's shape) or a bare bool.
    if isinstance(parsed, dict):
        parsed = parsed.get("enabled")
    if isinstance(parsed, bool):
        return parsed

    logger.warning(
        "tenant_codified_only is %s, expected a bool — keeping the gate ON",
        type(parsed).__name__,
    )
    return True


async def get_tenant_codified_only(*, conn=None) -> bool:
    """Is the tenant-facing compliance surface restricted to codified rows?"""
    global _tenant_codified_only_cache, _tenant_codified_only_cached_at

    now = time.monotonic()
    if (
        _tenant_codified_only_cache is not None
        and now - _tenant_codified_only_cached_at < VISIBLE_FEATURES_CACHE_TTL_SECONDS
    ):
        return _tenant_codified_only_cache

    try:
        if conn is None:
            async with get_connection() as managed_conn:
                raw = await managed_conn.fetchval(
                    "SELECT value FROM platform_settings WHERE key = 'tenant_codified_only'"
                )
        else:
            raw = await conn.fetchval(
                "SELECT value FROM platform_settings WHERE key = 'tenant_codified_only'"
            )
    except Exception:
        # A DB hiccup reading a display policy must not open the gate.
        logger.exception("tenant_codified_only read failed; keeping the gate ON")
        return True

    enabled = _normalize_tenant_codified_only(raw)
    _tenant_codified_only_cache = enabled
    _tenant_codified_only_cached_at = now
    return enabled


def invalidate_er_similarity_weights_cache() -> None:
    global _er_similarity_weights_cache, _er_similarity_weights_cached_at
    _er_similarity_weights_cache = None
    _er_similarity_weights_cached_at = 0.0


def prime_er_similarity_weights_cache(weights: dict[str, float]) -> dict[str, float]:
    global _er_similarity_weights_cache, _er_similarity_weights_cached_at
    _er_similarity_weights_cache = dict(weights)
    _er_similarity_weights_cached_at = time.monotonic()
    return dict(weights)


async def get_er_similarity_weights(*, conn=None) -> dict[str, float]:
    global _er_similarity_weights_cache, _er_similarity_weights_cached_at

    now = time.monotonic()
    if (
        _er_similarity_weights_cache is not None
        and now - _er_similarity_weights_cached_at < VISIBLE_FEATURES_CACHE_TTL_SECONDS
    ):
        return dict(_er_similarity_weights_cache)

    if conn is None:
        async with get_connection() as managed_conn:
            raw = await managed_conn.fetchval(
                "SELECT value FROM platform_settings WHERE key = 'er_similarity_weights'"
            )
    else:
        raw = await conn.fetchval(
            "SELECT value FROM platform_settings WHERE key = 'er_similarity_weights'"
        )

    if raw is None:
        return dict(DEFAULT_ER_SIMILARITY_WEIGHTS)

    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid er_similarity_weights payload; using defaults")
            return dict(DEFAULT_ER_SIMILARITY_WEIGHTS)

    if not isinstance(parsed, dict) or set(parsed.keys()) != EXPECTED_WEIGHT_KEYS:
        logger.warning("er_similarity_weights keys mismatch; using defaults")
        return dict(DEFAULT_ER_SIMILARITY_WEIGHTS)

    try:
        weights = {k: float(v) for k, v in parsed.items()}
    except (ValueError, TypeError):
        return dict(DEFAULT_ER_SIMILARITY_WEIGHTS)

    _er_similarity_weights_cache = weights
    _er_similarity_weights_cached_at = now
    return dict(weights)
