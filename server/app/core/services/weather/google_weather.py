"""Best-effort Google Weather daily forecast client.

The API key remains server-side and travels in the ``X-Goog-Api-Key``
header, never the query string, so an httpx error (whose message carries the
full request URL) cannot write it into the logs. ``None`` means unconfigured or failed while
``[]`` means Google returned a genuine empty forecast, allowing callers to
avoid persisting an outage as an empty weather week.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
DAILY_URL = "https://weather.googleapis.com/v1/forecast/days:lookup"


def _api_key() -> str | None:
    return get_settings().google_weather_api_key


def is_configured() -> bool:
    """Whether a forecast call can succeed at all — checked before anything
    spends a geocode on a location whose forecast could never be fetched."""
    return bool(_api_key())


def _number(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def parse_forecast_days(payload: dict) -> list[dict]:
    """Pure Google daily payload -> normalized rows, dropping invalid dates."""
    rows: list[dict] = []
    for item in payload.get("forecastDays") or []:
        display = item.get("displayDate") or {}
        try:
            local_date = date(
                int(display["year"]), int(display["month"]), int(display["day"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        period = item.get("daytimeForecast") or item.get("nighttimeForecast") or {}
        condition = (period.get("weatherCondition") or {}).get("type")
        precipitation = period.get("precipitation") or {}
        probability = (precipitation.get("probability") or {}).get("percent")
        qpf = precipitation.get("qpf") or {}
        rows.append({
            "local_date": local_date,
            "condition": condition,
            "precip_probability": int(probability) if probability is not None else None,
            "precip_qpf_mm": _number(qpf.get("quantity") if isinstance(qpf, dict) else None),
            "max_temp_c": _number((item.get("maxTemperature") or {}).get("degrees")),
            "min_temp_c": _number((item.get("minTemperature") or {}).get("degrees")),
            "raw": item,
        })
    return rows


async def fetch_daily_forecast(
    *, lat: float, lng: float, days: int = 10,
) -> list[dict] | None:
    key = _api_key()
    if not key:
        return None
    requested = max(1, min(int(days), 10))
    remaining = requested
    token: str | None = None
    rows: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=10.0, headers={"X-Goog-Api-Key": key},
        ) as client:
            for _ in range(2):
                params: dict[str, Any] = {
                    "location.latitude": lat,
                    "location.longitude": lng,
                    "days": requested,
                    "pageSize": requested,
                    "unitsSystem": "METRIC",
                }
                if token:
                    params["pageToken"] = token
                response = await client.get(DAILY_URL, params=params)
                response.raise_for_status()
                payload = response.json()
                rows.extend(parse_forecast_days(payload))
                token = payload.get("nextPageToken")
                remaining = max(0, requested - len(rows))
                if not token or not remaining:
                    break
        return rows[:requested]
    except Exception:
        logger.warning("Google Weather daily forecast failed", exc_info=True)
        return None
