"""Weather writes preserve the last forecast for past civil days."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.scheduling.autopilot import weather_store


@pytest.mark.asyncio
async def test_upsert_never_writes_past_days():
    conn = AsyncMock()
    conn.execute.return_value = "INSERT 0 1"
    today = date(2026, 9, 22)
    count = await weather_store.upsert_weather_days(
        conn, company_id=uuid4(), location_id=uuid4(), today=today,
        rows=[{"local_date": date(2026, 9, 21)}, {"local_date": today}],
    )
    assert count == 1
    assert conn.execute.await_count == 1
    query, *params = conn.execute.await_args.args
    assert "ON CONFLICT" in query and "EXCLUDED.local_date >= $10" in query
    assert params[2] == today and params[-1] == today


@pytest.mark.asyncio
async def test_load_is_tenant_and_location_scoped():
    conn = AsyncMock()
    day = date(2026, 9, 22)
    fetched_at = datetime(2026, 9, 22, tzinfo=timezone.utc)
    conn.fetch.return_value = [{
        "local_date": day, "condition": "RAIN", "precip_probability": 75,
        "precip_qpf_mm": None, "max_temp_c": 20, "min_temp_c": 10,
        "fetched_at": fetched_at,
    }]
    company_id, location_id = uuid4(), uuid4()
    result = await weather_store.load_weather_days(
        conn, company_id=company_id, location_id=location_id, start=day, end=day,
    )
    assert result[day]["precip_probability"] == 75
    query, *params = conn.fetch.await_args.args
    assert "company_id=$1 AND location_id=$2" in query
    assert params == [company_id, location_id, day, day]


@pytest.mark.asyncio
async def test_coordinates_short_circuit_and_geocode_failure(monkeypatch):
    conn = AsyncMock()
    conn.fetchrow.return_value = {"lat": 1.2, "lng": 3.4}
    company_id, location_id = uuid4(), uuid4()
    result = await weather_store.ensure_location_coordinates(
        conn, None, company_id=company_id, location_id=location_id,
    )
    assert result == (1.2, 3.4)
    conn.execute.assert_not_awaited()

    conn.fetchrow.return_value = {
        "lat": None, "lng": None, "address": "1 Main", "city": "Town",
        "state": "CA", "zipcode": "90001", "country_code": "US",
    }
    geocode = AsyncMock(return_value=None)
    monkeypatch.setattr(weather_store, "geocode", geocode)
    assert await weather_store.ensure_location_coordinates(
        conn, None, company_id=company_id, location_id=location_id,
    ) is None
    conn.execute.assert_not_awaited()

    geocode.return_value = {"lat": 9, "lng": 8, "source": "census"}
    assert await weather_store.ensure_location_coordinates(
        conn, None, company_id=company_id, location_id=location_id,
    ) == (9.0, 8.0)
    query, *params = conn.execute.await_args.args
    assert "geocoded_at=NOW()" in query
    assert params[-2:] == [location_id, company_id]


@pytest.mark.asyncio
async def test_coordinates_skip_non_us_missing_rows_and_errors(monkeypatch):
    conn = AsyncMock()
    geocode = AsyncMock(side_effect=AssertionError("US-only geocoder"))
    monkeypatch.setattr(weather_store, "geocode", geocode)
    conn.fetchrow.return_value = {"lat": None, "lng": None, "country_code": "CA",
                                  "address": "1 Main", "city": "Town", "state": "ON", "zipcode": "X"}
    assert await weather_store.ensure_location_coordinates(
        conn, None, company_id=uuid4(), location_id=uuid4(),
    ) is None
    conn.fetchrow.return_value = None
    assert await weather_store.ensure_location_coordinates(
        conn, None, company_id=uuid4(), location_id=uuid4(),
    ) is None
    conn.fetchrow.side_effect = RuntimeError("db down")
    assert await weather_store.ensure_location_coordinates(
        conn, None, company_id=uuid4(), location_id=uuid4(),
    ) is None


@pytest.mark.asyncio
async def test_refresh_needs_a_civil_timezone_coordinates_and_a_forecast(monkeypatch):
    company_id, location_id = uuid4(), uuid4()
    coords = AsyncMock(return_value=None)
    fetch = AsyncMock(return_value=None)
    upsert = AsyncMock(return_value=1)
    load = AsyncMock(return_value={"loaded": True})
    monkeypatch.setattr(weather_store, "ensure_location_coordinates", coords)
    monkeypatch.setattr(weather_store, "fetch_daily_forecast", fetch)
    monkeypatch.setattr(weather_store, "upsert_weather_days", upsert)
    monkeypatch.setattr(weather_store, "load_weather_days", load)

    for tz in (None, "Not/AZone"):
        conn = AsyncMock()
        conn.fetchrow.return_value = {"timezone": tz}
        assert await weather_store.refresh_location_weather(
            conn, company_id=company_id, location_id=location_id,
        ) == {}
    coords.assert_not_awaited()

    conn = AsyncMock()
    conn.fetchrow.return_value = {"timezone": "America/Los_Angeles"}
    assert await weather_store.refresh_location_weather(conn, company_id=company_id, location_id=location_id) == {}
    fetch.assert_not_awaited()

    coords.return_value = (37.0, -122.0)
    assert await weather_store.refresh_location_weather(conn, company_id=company_id, location_id=location_id) == {}
    upsert.assert_not_awaited()   # an outage is never written as an empty week

    fetch.return_value = [{"local_date": date(2026, 9, 22)}]
    assert await weather_store.refresh_location_weather(
        conn, company_id=company_id, location_id=location_id,
    ) == {"loaded": True}
    assert upsert.await_args.kwargs["rows"] == fetch.return_value
