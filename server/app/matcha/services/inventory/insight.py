"""Grounded, optional Luna interpretation for inventory conclusions.

The model only sees server-formatted display tokens. It may choose wording and
an allowed action, but never numbers, raw ids, or a diagnosis outside the
deterministic veto table.
"""
import hashlib
import json
import re
from typing import Any

import httpx

from app.config import get_settings
from app.core.services.redis_cache import cache_get, cache_set, get_redis_cache
from app.matcha.services.inventory.waste.agent import _response_text

_NUMERIC = re.compile(r"[$%]|\d")
_ACTIONS = {"right_size_par", "review_handling", "check_rotation", "count_stock", "none"}
_ACTION_FOR_DIAGNOSIS = {"over_ordering": "right_size_par", "handling": "review_handling", "unexplained_shrink": "count_stock", "external": "none", "mixed": "none"}


def _render(template: str, tokens: dict[str, str]) -> str | None:
    if _NUMERIC.search(template):
        return None
    names = set(re.findall(r"\{([a-z_]+)\}", template))
    if any(name not in tokens for name in names):
        return None
    return re.sub(r"\{([a-z_]+)\}", lambda match: tokens[match.group(1)], template)


def deterministic_insight(*, diagnosis: str, tokens: dict[str, str]) -> dict:
    action = _ACTION_FOR_DIAGNOSIS.get(diagnosis, "none")
    if diagnosis == "over_ordering":
        headline, detail = "Loss points to over-ordering.", "Review the PAR before the next purchase."
    elif diagnosis == "handling":
        headline, detail = "Loss points to handling rather than demand.", "Review preparation, storage, and rotation before changing a PAR."
    elif diagnosis == "unexplained_shrink":
        headline, detail = "Loss needs a stock-count check.", "Review the movement ledger and count the affected stock."
    else:
        headline, detail = "No single loss cause is decisive.", "Keep watching the pattern before changing inventory targets."
    return {"headline": headline, "diagnosis": diagnosis, "action": action, "confidence": "deterministic", "detail": detail}


async def interpret(*, surface: str, diagnosis: str, tokens: dict[str, str]) -> dict:
    """Return a validated Luna wording or a deterministic conclusion."""
    fallback = deterministic_insight(diagnosis=diagnosis, tokens=tokens)
    fingerprint = hashlib.sha256(json.dumps([surface, diagnosis, tokens], sort_keys=True).encode()).hexdigest()
    redis = get_redis_cache()
    key = f"inventory:insight:{fingerprint}"
    if redis:
        cached = await cache_get(redis, key)
        if cached:
            return cached
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_luna_model:
        return fallback
    prompt = (
        "Write a concise inventory-manager conclusion as strict JSON with headline, diagnosis, action, confidence, and detail. "
        "Use only {token} placeholders for every numeric or date reference; never write a digit, dollar sign, or percent sign. "
        f"Diagnosis must be {diagnosis!r}. Action must be exactly {_ACTION_FOR_DIAGNOSIS.get(diagnosis, 'none')!r}. "
        f"Surface: {surface}. Available tokens: {json.dumps(tokens, separators=(',', ':'))}."
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {settings.openai_api_key}"}, json={"model": settings.openai_luna_model, "input": prompt})
            response.raise_for_status()
        raw = json.loads(_response_text(response.json()))
        if not isinstance(raw, dict) or raw.get("diagnosis") != diagnosis or raw.get("action") not in _ACTIONS or raw.get("action") != _ACTION_FOR_DIAGNOSIS.get(diagnosis, "none"):
            return fallback
        rendered = {field: _render(str(raw.get(field, "")), tokens) for field in ("headline", "detail")}
        if not rendered["headline"] or not rendered["detail"]:
            return fallback
        result = {**raw, **rendered}
        if redis: await cache_set(redis, key, result, ttl=900)
        return result
    except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
        return fallback
