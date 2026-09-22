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
