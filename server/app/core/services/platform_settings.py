"""Helpers for frequently-read platform settings."""

import json
import logging
import time
from typing import Sequence
from uuid import UUID

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
    "matcha_ops",
]
DEFAULT_MATCHA_WORK_MODEL_MODE = "light"
DEFAULT_JURISDICTION_RESEARCH_MODEL_MODE = "light"
# The legacy single "Agent model" row. It now only seeds the per-app map
# (`agent_models`, below) until an admin first saves that map.
DEFAULT_AGENT_MODEL = "default"
AGENT_MODEL_CHOICES = ("default", "claude-haiku-5-5", "claude-sonnet-5-5")
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

# Per-board AutoPR capability grants: {project_id: [capability, ...]}.
#
# The hardcoded KANBAN_AUTOPR_PROJECT_IDS allowlist in project_task_service.py
# stays the outer boundary — a board absent from it has no harness polling it
# and can never be granted anything here. This map is the INNER gate, and it is
# what makes the lane safe to extend beyond code review: "research" reads the
# world and writes a report, "outreach" lets a human approve and send an email
# the model drafted, "browse" lets a run drive a real browser and attach
# screenshots, "email" lets a run read the email snapshots a person attached
# to an email card and draft replies (sending those still needs "outreach" and a
# per-item human approval). Each is a different blast radius, so each is
# granted separately and every one of them defaults OFF.
AUTOPR_BOARD_CAPABILITIES = ("research", "outreach", "browse", "email")
DEFAULT_AUTOPR_BOARD_CAPABILITIES: dict[str, list[str]] = {}

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

_autopr_board_capabilities_cache: dict[str, list[str]] | None = None
_autopr_board_capabilities_cached_at: float = 0.0

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


# ── AI models per app and product (`agent_models`) ──
#
# {"apps": {"matcha": choice, ...}, "surfaces": {"matcha.ir": choice | "inherit", ...}}
# where choice is "default" (the surface's built-in provider) or a Claude id.
# The registry of apps and surfaces is `core/services/agent_surfaces.py`;
# `anthropic_messages.claude_override(surface)` is the one reader that routes.
# Read on every Huume turn, EMS message and routed Gemini call, so every
# resolution is cached, the no-row default included.

_agent_models_cache: dict | None = None
_agent_models_cached_at: float = 0.0


def normalize_agent_models(parsed: object) -> dict:
    """The stored map in its full shape: every app and every registered
    surface present, unknown keys and values dropped (an app → "default", a
    surface → "inherit"). Lenient on purpose — a registry that has since
    shrunk, or one bad value, must not unset the rest."""
    from app.core.services import agent_surfaces as reg

    apps_in = parsed.get("apps") if isinstance(parsed, dict) else None
    surfaces_in = parsed.get("surfaces") if isinstance(parsed, dict) else None
    apps_in = apps_in if isinstance(apps_in, dict) else {}
    surfaces_in = surfaces_in if isinstance(surfaces_in, dict) else {}
    return {
        "apps": {
            app.key: apps_in.get(app.key) if apps_in.get(app.key) in reg.MODEL_CHOICES else reg.BUILTIN
            for app in reg.APPS
        },
        "surfaces": {
            s.key: surfaces_in.get(s.key) if surfaces_in.get(s.key) in reg.SURFACE_CHOICES else reg.INHERIT
            for s in reg.SURFACES
        },
    }


def _agent_models_from_legacy(legacy: object) -> dict:
    """Before the first save of `agent_models`: the old single setting drove
    Matcha and Espresso, so both app defaults take its value and every
    product inherits. Deploying the split therefore changes nothing."""
    from app.core.services import agent_surfaces as reg

    value = legacy if legacy in reg.MODEL_CHOICES else reg.BUILTIN
    return normalize_agent_models({"apps": {reg.MATCHA: value, reg.ESPRESSO: value}})


def prime_agent_models_cache(value: object) -> dict:
    """Seed the cache straight after an admin write; returns the normalized map."""
    global _agent_models_cache, _agent_models_cached_at
    _agent_models_cache = normalize_agent_models(value)
    _agent_models_cached_at = time.monotonic()
    return _copy_agent_models(_agent_models_cache)


def _copy_agent_models(models: dict) -> dict:
    return {"apps": dict(models["apps"]), "surfaces": dict(models["surfaces"])}


def _json_value(raw: object) -> object:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


async def get_agent_models(*, conn=None) -> dict:
    """The full per-app/per-surface map, from `agent_models`, or seeded from
    the legacy `agent_model` row while `agent_models` has never been saved."""
    global _agent_models_cache, _agent_models_cached_at
    now = time.monotonic()
    if _agent_models_cache is not None and now - _agent_models_cached_at < VISIBLE_FEATURES_CACHE_TTL_SECONDS:
        return _copy_agent_models(_agent_models_cache)

    query = "SELECT key, value FROM platform_settings WHERE key IN ('agent_models', 'agent_model')"
    if conn is None:
        async with get_connection() as managed_conn:
            rows = await managed_conn.fetch(query)
    else:
        rows = await conn.fetch(query)
    stored = {row["key"]: _json_value(row["value"]) for row in rows}

    if "agent_models" in stored:
        models = normalize_agent_models(stored["agent_models"])
    else:
        models = _agent_models_from_legacy(stored.get("agent_model"))
    _agent_models_cache = models
    _agent_models_cached_at = now
    return _copy_agent_models(models)


def resolve_agent_model(models: dict, surface: str) -> str:
    """One surface's effective choice: its own value unless `inherit`, else
    its app default, else "default". An unknown surface follows the app its
    key prefix names (and is logged), so a typo never routes to Claude by
    surprise and never crashes a turn."""
    from app.core.services import agent_surfaces as reg

    if surface not in reg.SURFACE_BY_KEY:
        logger.warning("agent model: unregistered surface %r; using its app default", surface)
    own = models.get("surfaces", {}).get(surface, reg.INHERIT)
    if own in reg.MODEL_CHOICES:
        return own
    app = reg.app_of(surface)
    return models.get("apps", {}).get(app, reg.BUILTIN) if app else reg.BUILTIN


async def get_agent_model(surface: str, *, conn=None) -> str:
    """The effective model choice for one surface (see `resolve_agent_model`)."""
    return resolve_agent_model(await get_agent_models(conn=conn), surface)


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


def _normalize_autopr_board_capabilities(parsed: object) -> dict[str, list[str]] | None:
    """Shape check for the stored map. Returns None when it is unusable, so
    every caller falls back to "no board has any capability" rather than to a
    half-parsed grant."""
    if not isinstance(parsed, dict):
        return None
    normalized: dict[str, list[str]] = {}
    for raw_project_id, raw_caps in parsed.items():
        if not isinstance(raw_project_id, str) or not isinstance(raw_caps, list):
            return None
        try:
            project_id = str(UUID(raw_project_id))
        except (ValueError, AttributeError, TypeError):
            return None
        caps: list[str] = []
        for cap in raw_caps:
            if not isinstance(cap, str) or cap not in AUTOPR_BOARD_CAPABILITIES:
                return None
            if cap not in caps:
                caps.append(cap)
        normalized[project_id] = caps
    return normalized


def prime_autopr_board_capabilities_cache(value: dict[str, list[str]]) -> dict[str, list[str]]:
    """Seed the cache straight after an admin write, so the next read does not
    serve the previous grant for up to the cache TTL."""
    global _autopr_board_capabilities_cache, _autopr_board_capabilities_cached_at
    normalized = _normalize_autopr_board_capabilities(value) or {}
    _autopr_board_capabilities_cache = normalized
    _autopr_board_capabilities_cached_at = time.monotonic()
    return {k: list(v) for k, v in normalized.items()}


async def get_autopr_board_capabilities(*, conn=None) -> dict[str, list[str]]:
    """Which AutoPR capabilities each Espresso board has been granted.

    Fail-closed in every direction: an absent row, an unparseable value, an
    unknown capability name, or a non-UUID key all resolve to the empty map.
    A board with no entry has no capability — the lane still opens code PRs
    there, which is the behavior that predates this setting.

    Every resolution is cached, the fallbacks included. No row at all is the
    documented default, so leaving that case uncached made the steady state the
    one that queried Postgres on every capability check — and re-logged the
    malformed-payload warning on every request, with no backoff.
    """
    global _autopr_board_capabilities_cache, _autopr_board_capabilities_cached_at

    now = time.monotonic()
    if (
        _autopr_board_capabilities_cache is not None
        and now - _autopr_board_capabilities_cached_at < VISIBLE_FEATURES_CACHE_TTL_SECONDS
    ):
        return {k: list(v) for k, v in _autopr_board_capabilities_cache.items()}

    if conn is None:
        async with get_connection() as managed_conn:
            raw = await managed_conn.fetchval(
                "SELECT value FROM platform_settings WHERE key = 'autopr_board_capabilities'"
            )
    else:
        raw = await conn.fetchval(
            "SELECT value FROM platform_settings WHERE key = 'autopr_board_capabilities'"
        )

    def _cache(value: dict[str, list[str]]) -> dict[str, list[str]]:
        global _autopr_board_capabilities_cache, _autopr_board_capabilities_cached_at
        _autopr_board_capabilities_cache = value
        _autopr_board_capabilities_cached_at = now
        return {k: list(v) for k, v in value.items()}

    if raw is None:
        return _cache(dict(DEFAULT_AUTOPR_BOARD_CAPABILITIES))

    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid autopr_board_capabilities payload; granting nothing")
            return _cache(dict(DEFAULT_AUTOPR_BOARD_CAPABILITIES))

    normalized = _normalize_autopr_board_capabilities(parsed)
    if normalized is None:
        logger.warning("Malformed autopr_board_capabilities payload; granting nothing")
        return _cache(dict(DEFAULT_AUTOPR_BOARD_CAPABILITIES))

    return _cache(normalized)


async def board_has_autopr_capability(project_id, capability: str, *, conn=None) -> bool:
    """One board, one capability. The single read every gate should use."""
    if capability not in AUTOPR_BOARD_CAPABILITIES:
        return False
    grants = await get_autopr_board_capabilities(conn=conn)
    return capability in grants.get(str(project_id), [])
