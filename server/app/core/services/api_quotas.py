"""What the paid search APIs have left this period, for Admin → AI Usage.

- Brave reports its quota on every response (its rate-limit headers);
  `matcha_work/brave_search.py` saves the latest one through
  `ai_usage.save_api_quota` as `platform_settings['api_quota.brave']`. Nothing
  is asked here: a request to Brave costs a search.
- SerpApi and SearchAPI have account endpoints that are free and don't count
  against the quota (`serpapi.com/account.json`, `searchapi.io/api/v1/me`).
  Both are asked live, at once, with a short timeout.
- Google Places has no quota API; its requests and cost are in the ledger.

A key never leaves this module: a failure is reported as a status code or an
exception name, never httpx's message, which carries the URL and its
`api_key`.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.core.services.ai_usage import API_PRICING, BRAVE_PRICE_ENV, QUOTA_KEY_PREFIX, api_price

SERPAPI_ACCOUNT_URL = "https://serpapi.com/account.json"
SEARCHAPI_ACCOUNT_URL = "https://www.searchapi.io/api/v1/me"
TIMEOUT_SECONDS = 8.0


def _card(provider: str, label: str, *, configured: bool, source: str | None, **fields: Any) -> dict[str, Any]:
    card: dict[str, Any] = {
        "provider": provider, "label": label, "configured": configured, "source": source,
        "plan": None, "monthly_price": None, "limit": None, "remaining": None, "used": None,
        "extra_credits": None, "resets_at": None, "observed_at": None, "error": None, "note": None,
    }
    card.update(fields)
    if card["used"] is None and isinstance(card["limit"], int) and isinstance(card["remaining"], int):
        card["used"] = max(card["limit"] - card["remaining"], 0)
    return card


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _text(value: Any) -> str | None:
    return value[:100] if isinstance(value, str) and value else None


def _settings() -> Any:
    from app.config import get_settings

    try:
        return get_settings()
    except RuntimeError:  # settings not loaded (a bare script, some tests)
        return None


def _key(name: str) -> str | None:
    settings = _settings()
    return (getattr(settings, name, None) or None) if settings is not None else None


async def _get_json(url: str, *, params: dict, headers: dict | None = None,
                    transport: httpx.AsyncBaseTransport | None = None) -> tuple[dict | None, str | None]:
    """(body, None) or (None, why it failed), without the key in the why."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=transport) as client:
            response = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        return None, type(exc).__name__
    if response.status_code >= 400:
        return None, f"answered {response.status_code}"
    try:
        body = response.json()
    except ValueError:
        return None, "returned something other than JSON"
    return (body, None) if isinstance(body, dict) else (None, "returned an unexpected shape")


def _brave_price_note() -> str:
    price = api_price("brave", "web_search") or 0.0
    if price == 0:
        return f"Counted at $0 a search ({BRAVE_PRICE_ENV}=0)."
    return f"Counted at ${price * 1000:g} per 1,000 searches; set {BRAVE_PRICE_ENV} to your plan's rate (0 on Free)."


async def brave(conn: Any) -> dict[str, Any]:
    configured = _key("brave_search_api_key") is not None
    raw = await conn.fetchval("SELECT value FROM platform_settings WHERE key = $1", f"{QUOTA_KEY_PREFIX}brave")
    seen = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(seen, dict):
        return _card("brave", "Brave Search", configured=configured, source="headers",
                     note=f"Searches left appear after the next search. {_brave_price_note()}")
    return _card(
        "brave", "Brave Search", configured=configured, source="headers",
        limit=_int(seen.get("limit")), remaining=_int(seen.get("remaining")),
        resets_at=_text(seen.get("resets_at")), observed_at=_text(seen.get("observed_at")),
        note=f"As of Brave's answer to the latest search. {_brave_price_note()}",
    )


async def serpapi(*, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    key = _key("serp_api_key")
    if key is None:
        return _card("serpapi", "SerpApi", configured=False, source="account_api")
    body, error = await _get_json(SERPAPI_ACCOUNT_URL, params={"api_key": key}, transport=transport)
    if body is None:
        return _card("serpapi", "SerpApi", configured=True, source="account_api", error=f"SerpApi {error}")
    remaining = _int(body.get("total_searches_left"))
    return _card(
        "serpapi", "SerpApi", configured=True, source="account_api",
        plan=_text(body.get("plan_name")), monthly_price=_number(body.get("plan_monthly_price")),
        limit=_int(body.get("searches_per_month")),
        remaining=remaining if remaining is not None else _int(body.get("plan_searches_left")),
        used=_int(body.get("this_month_usage")), extra_credits=_int(body.get("extra_credits")),
        resets_at=_text(body.get("plan_renewal_date")),
    )


async def searchapi(*, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    key = _key("search_api_key")
    if key is None:
        return _card("searchapi", "SearchAPI", configured=False, source="account_api")
    body, error = await _get_json(SEARCHAPI_ACCOUNT_URL, params={"api_key": key},
                                  headers={"Authorization": f"Bearer {key}"}, transport=transport)
    if body is None:
        return _card("searchapi", "SearchAPI", configured=True, source="account_api", error=f"SearchAPI {error}")
    account = body.get("account") if isinstance(body.get("account"), dict) else {}
    subscription = body.get("subscription") if isinstance(body.get("subscription"), dict) else {}
    return _card(
        "searchapi", "SearchAPI", configured=True, source="account_api",
        limit=_int(account.get("monthly_allowance")), remaining=_int(account.get("remaining_credits")),
        used=_int(account.get("current_month_usage")), resets_at=_text(subscription.get("period_end")),
        note=None if subscription else "No active subscription reported.",
    )


def google_places() -> dict[str, Any]:
    pro = API_PRICING[("google_places", "text_search_pro")]
    enterprise = API_PRICING[("google_places", "text_search_enterprise")]
    return _card(
        "google_places", "Google Places", configured=_key("google_maps_api_key") is not None, source=None,
        note=(f"No quota API. Text Search at ${enterprise * 1000:g} (Enterprise) / ${pro * 1000:g} (Pro) "
              "per 1,000; Google's free monthly calls aren't netted out."),
    )


async def all_quotas(brave_card: dict[str, Any], *,
                     transport: httpx.AsyncBaseTransport | None = None) -> list[dict[str, Any]]:
    """Every card: Brave's (read by the caller, so no connection is held
    while the account APIs answer), then the ones asked live."""
    serp, search = await asyncio.gather(serpapi(transport=transport), searchapi(transport=transport))
    return [brave_card, search, serp, google_places()]
