"""Google Weather normalization and failure behavior."""

from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.core.services.weather import google_weather


def _day(day, *, daytime=None, nighttime=None):
    return {
        "displayDate": {"year": 2026, "month": 9, "day": day},
        "daytimeForecast": daytime,
        "nighttimeForecast": nighttime,
        "maxTemperature": {"degrees": 25.5},
        "minTemperature": {"degrees": 12},
    }


def test_parse_daytime_nighttime_and_missing_precipitation():
    payload = {"forecastDays": [
        _day(22, daytime={"weatherCondition": {"type": "RAIN"},
                           "precipitation": {"probability": {"percent": 65},
                                             "qpf": {"quantity": 4.25}}}),
        _day(23, nighttime={"weatherCondition": {"type": "CLEAR"}}),
        {"displayDate": {"year": 2026, "month": 13, "day": 1}},
    ]}
    rows = google_weather.parse_forecast_days(payload)
    assert [row["local_date"] for row in rows] == [date(2026, 9, 22), date(2026, 9, 23)]
    assert (rows[0]["condition"], rows[0]["precip_probability"]) == ("RAIN", 65)
    assert str(rows[0]["precip_qpf_mm"]) == "4.25"
    assert rows[1]["condition"] == "CLEAR"
    assert rows[1]["precip_probability"] is None


@pytest.mark.asyncio
async def test_fetch_without_key_does_not_open_network(monkeypatch):
    monkeypatch.setattr(google_weather, "get_settings", lambda: SimpleNamespace(google_weather_api_key=None))
    assert await google_weather.fetch_daily_forecast(lat=1, lng=2) is None


@pytest.mark.asyncio
async def test_fetch_follows_second_page_and_fails_closed(monkeypatch):
    monkeypatch.setattr(google_weather, "get_settings", lambda: SimpleNamespace(google_weather_api_key="test"))
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, *, params):
            calls.append(params)
            return Response(
                {"forecastDays": [_day(22)], "nextPageToken": "next"}
                if len(calls) == 1 else {"forecastDays": [_day(23)]}
            )

    monkeypatch.setattr(google_weather.httpx, "AsyncClient", Client)
    rows = await google_weather.fetch_daily_forecast(lat=1, lng=2, days=2)
    assert [row["local_date"].day for row in rows] == [22, 23]
    assert calls[1]["pageToken"] == "next"
    assert calls[1]["days"] == calls[0]["days"] == 2

    class FailedClient(Client):
        async def get(self, _url, *, params):
            raise httpx.ConnectError("unavailable")

    monkeypatch.setattr(google_weather.httpx, "AsyncClient", FailedClient)
    assert await google_weather.fetch_daily_forecast(lat=1, lng=2) is None
