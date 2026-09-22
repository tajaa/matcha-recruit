"""Autopilot database inputs must cover the forecast's history window."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.scheduling.autopilot import inputs
from app.matcha.services.scheduling.autopilot.forecast import weekday_baseline
from app.matcha.services.scheduling.autopilot.policy import POLICY_SALES_HISTORY_DAYS


@pytest.mark.asyncio
async def test_sales_loader_includes_earliest_forecast_day(monkeypatch):
    week_start = date(2026, 9, 21)
    oldest_day = week_start - timedelta(days=POLICY_SALES_HISTORY_DAYS)
    sales = {oldest_day: Decimal(123)}
    load_sales = AsyncMock(return_value=sales)
    monkeypatch.setattr(inputs, "load_sales_by_day", load_sales)
    monkeypatch.setattr(inputs, "_fresh_weather", AsyncMock(return_value={}))
    monkeypatch.setattr(inputs, "load_schedule_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(inputs, "load_blended_hourly_rate", AsyncMock(return_value=None))
    conn = AsyncMock()
    conn.fetch.return_value = []
    company_id, location_id = uuid4(), uuid4()

    loaded = await inputs.load_autopilot_inputs(
        conn, company_id=company_id, location_id=location_id,
        week_start=week_start, roster={}, profile_bundle={},
    )

    load_sales.assert_awaited_once_with(
        conn, company_id=company_id, location_id=location_id,
        start=oldest_day, end=week_start - timedelta(days=1),
    )
    assert weekday_baseline(
        week_start, sales_by_day=loaded["sales_by_day"], anchor=week_start,
    ) == (Decimal(123), 1, "trailing_mean")


def _weather(days, fetched_at):
    return {day: {"precip_probability": 10, "fetched_at": fetched_at} for day in days}


@pytest.mark.asyncio
async def test_week_past_forecast_horizon_never_calls_the_provider(monkeypatch):
    from datetime import datetime, timezone

    refresh = AsyncMock(side_effect=AssertionError("no provider call expected"))
    monkeypatch.setattr(inputs, "refresh_location_weather", refresh)
    monkeypatch.setattr(inputs, "load_weather_days", AsyncMock(return_value={}))
    today = date(2026, 9, 1)
    rows = await inputs._fresh_weather(
        AsyncMock(), company_id=uuid4(), location_id=uuid4(),
        week_start=today + timedelta(days=14), today=today,
    )
    assert rows == {}
    refresh.assert_not_awaited()

    # A fresh, complete in-horizon week is reused as stored.
    week = today + timedelta(days=2)
    stored = _weather([week + timedelta(days=i) for i in range(7)], datetime.now(timezone.utc))
    monkeypatch.setattr(inputs, "load_weather_days", AsyncMock(return_value=stored))
    assert await inputs._fresh_weather(
        AsyncMock(), company_id=uuid4(), location_id=uuid4(), week_start=week, today=today,
    ) == stored


@pytest.mark.asyncio
async def test_stale_or_missing_in_horizon_days_refresh_best_effort(monkeypatch):
    from datetime import datetime, timezone

    today = date(2026, 9, 1)
    week = today + timedelta(days=5)          # days 5..11; horizon ends day 9
    old = datetime.now(timezone.utc) - timedelta(hours=30)
    stale = _weather([week + timedelta(days=i) for i in range(5)], old)
    fresh = _weather([week], datetime.now(timezone.utc))
    monkeypatch.setattr(inputs, "load_weather_days", AsyncMock(side_effect=[stale, fresh]))
    refresh = AsyncMock()
    monkeypatch.setattr(inputs, "refresh_location_weather", refresh)
    assert await inputs._fresh_weather(
        AsyncMock(), company_id=uuid4(), location_id=uuid4(), week_start=week, today=today,
    ) == fresh
    refresh.assert_awaited_once()

    # A provider failure keeps the stored rows instead of failing the build.
    monkeypatch.setattr(inputs, "load_weather_days", AsyncMock(return_value=stale))
    monkeypatch.setattr(inputs, "refresh_location_weather", AsyncMock(side_effect=RuntimeError("down")))
    assert await inputs._fresh_weather(
        AsyncMock(), company_id=uuid4(), location_id=uuid4(), week_start=week, today=today,
    ) == stale


@pytest.mark.asyncio
async def test_location_without_timezone_skips_refresh(monkeypatch):
    monkeypatch.setattr(inputs, "load_weather_days", AsyncMock(return_value={}))
    refresh = AsyncMock(side_effect=AssertionError("no provider call expected"))
    monkeypatch.setattr(inputs, "refresh_location_weather", refresh)
    for tz in (None, "Not/AZone"):
        conn = AsyncMock()
        conn.fetchval.return_value = tz
        assert await inputs._fresh_weather(
            conn, company_id=uuid4(), location_id=uuid4(), week_start=date(2026, 9, 21),
        ) == {}


@pytest.mark.asyncio
async def test_loaders_are_location_scoped_and_published_only():
    conn = AsyncMock()
    conn.fetch.return_value = [{"business_date": date(2026, 9, 1), "gross_sales": 12.5}]
    company_id, location_id = uuid4(), uuid4()
    sales = await inputs.load_sales_by_day(
        conn, company_id=company_id, location_id=location_id,
        start=date(2026, 6, 1), end=date(2026, 9, 20),
    )
    assert sales == {date(2026, 9, 1): Decimal("12.5")}
    sql = conn.fetch.await_args.args[0]
    # A company-wide import cannot size one store.
    assert "si.location_id=$2" in sql and "location_id IS NULL" not in sql

    conn.fetch.return_value = [{"starts_at": 1}]
    history = await inputs.load_schedule_history(
        conn, company_id=company_id, location_id=location_id, week_start=date(2026, 9, 21),
    )
    assert history == [{"starts_at": 1}]
    sql = conn.fetch.await_args.args[0]
    assert "s.status='published'" in sql and "LIMIT 2000" in sql

    conn.fetchval.side_effect = [None, 18.5]
    assert await inputs.load_blended_hourly_rate(
        conn, company_id=company_id, location_id=location_id,
    ) == Decimal("18.5")
    conn.fetchval.side_effect = [None, None]
    assert await inputs.load_blended_hourly_rate(
        conn, company_id=company_id, location_id=location_id,
    ) is None
