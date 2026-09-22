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
    monkeypatch.setattr(inputs, "load_weather_days", AsyncMock(return_value={}))
    monkeypatch.setattr(inputs, "load_location_holidays", AsyncMock(return_value={}))
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


def test_refresh_is_needed_only_when_a_provider_call_can_help():
    from datetime import datetime, timezone

    today = date(2026, 9, 1)
    now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    week = today + timedelta(days=2)
    fresh = _weather([week + timedelta(days=i) for i in range(7)], now)
    # Wholly past the 10-day horizon, or already over: nothing to fetch.
    assert not inputs.weather_refresh_needed({}, week_start=today + timedelta(days=14), today=today, now=now)
    assert not inputs.weather_refresh_needed({}, week_start=today - timedelta(days=14), today=today, now=now)
    # A fresh, complete in-horizon week is reused as stored.
    assert not inputs.weather_refresh_needed(fresh, week_start=week, today=today, now=now)
    # Stale, or missing an in-horizon day, is worth a call.
    stale = _weather(list(fresh), now - timedelta(hours=30))
    assert inputs.weather_refresh_needed(stale, week_start=week, today=today, now=now)
    assert inputs.weather_refresh_needed(_weather([week], now), week_start=week, today=today, now=now)


class _TrackedConnection:
    def __init__(self, conn, events):
        self.conn, self.events = conn, events

    async def __aenter__(self):
        self.events.append("open")
        return self.conn

    async def __aexit__(self, *_exc):
        self.events.append("close")
        return False


@pytest.mark.asyncio
async def test_weather_refresh_runs_with_no_connection_held(monkeypatch):
    events: list[str] = []
    conn = AsyncMock()
    conn.fetchval.return_value = "America/Los_Angeles"
    monkeypatch.setattr(inputs, "connection_or_direct", lambda: _TrackedConnection(conn, events))
    features = AsyncMock(return_value={"schedule_autopilot": True})
    monkeypatch.setattr(inputs, "get_company_features", features)
    monkeypatch.setattr(inputs, "load_weather_days", AsyncMock(return_value={}))

    async def refresh(**_kwargs):
        events.append("refresh")

    monkeypatch.setattr(inputs, "refresh_location_weather", refresh)
    today = date(2026, 9, 1)
    args = {"company_id": uuid4(), "location_id": uuid4(), "week_start": today + timedelta(days=2)}
    await inputs.ensure_autopilot_weather(**args, today=today)
    assert events == ["open", "close", "refresh"]

    # The location's own civil date decides the horizon when none is given.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    events.clear()
    local_today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    await inputs.ensure_autopilot_weather(**{**args, "week_start": local_today + timedelta(days=1)})
    assert events == ["open", "close", "refresh"]

    # Not entitled, no usable timezone, or past the horizon: no provider call.
    for tz, flags, week_start in (
        ("America/Los_Angeles", {}, local_today),
        ("Not/AZone", {"schedule_autopilot": True}, local_today),
        (None, {"schedule_autopilot": True}, local_today),
        ("America/Los_Angeles", {"schedule_autopilot": True}, local_today + timedelta(days=21)),
    ):
        events.clear()
        conn.fetchval.return_value = tz
        features.return_value = flags
        await inputs.ensure_autopilot_weather(**{**args, "week_start": week_start})
        assert "refresh" not in events

    # A provider failure never fails the build.
    features.return_value = {"schedule_autopilot": True}

    async def boom(**_kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(inputs, "refresh_location_weather", boom)
    await inputs.ensure_autopilot_weather(**args, today=today)


@pytest.mark.asyncio
async def test_holidays_only_for_us_or_unknown_country_stores():
    conn = AsyncMock()
    start, end = date(2026, 11, 20), date(2026, 11, 30)
    conn.fetchval.return_value = "US"
    holidays = await inputs.load_location_holidays(
        conn, company_id=uuid4(), location_id=uuid4(), start=start, end=end,
    )
    assert holidays == {date(2026, 11, 26): "Thanksgiving", date(2026, 11, 27): "Black Friday"}
    conn.fetchval.return_value = None
    assert await inputs.load_location_holidays(
        conn, company_id=uuid4(), location_id=uuid4(), start=start, end=end,
    ) == holidays
    conn.fetchval.return_value = "CA"
    assert await inputs.load_location_holidays(
        conn, company_id=uuid4(), location_id=uuid4(), start=start, end=end,
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
