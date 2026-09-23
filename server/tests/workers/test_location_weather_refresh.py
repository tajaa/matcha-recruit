"""The weather sweep obeys its gate, claim, tenant flag, and civil timezone."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.workers.tasks import location_weather_refresh as worker


class _Conn:
    def __init__(self, *, claimed=True, rows=()):
        self.claimed = claimed
        self.rows = list(rows)
        self.query = None
        self.closed = False

    async def fetchval(self, *_args):
        return self.claimed

    async def fetch(self, query, *_args):
        self.query = query
        return self.rows

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _weather_key(monkeypatch):
    monkeypatch.setattr(worker, "is_configured", lambda: True)


@pytest.mark.asyncio
async def test_unconfigured_key_skips_before_claiming_or_geocoding(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(worker, "is_configured", lambda: False)
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(worker, "scheduler_settings_row", AsyncMock(return_value={
        "enabled": True, "max_per_cycle": 50,
    }))
    coords = AsyncMock(side_effect=AssertionError("no geocode without a key"))
    monkeypatch.setattr(worker, "ensure_location_coordinates", coords)
    assert await worker._run() == {"status": "unconfigured"}
    assert conn.query is None and conn.closed


@pytest.mark.asyncio
async def test_disabled_and_unclaimed_sweeps_do_not_fetch(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(worker, "scheduler_settings_row", AsyncMock(return_value={"enabled": False}))
    assert await worker._run() == {"status": "disabled"}
    assert conn.query is None and conn.closed

    conn = _Conn(claimed=False)
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(worker, "scheduler_settings_row", AsyncMock(return_value={
        "enabled": True, "max_per_cycle": 50,
    }))
    assert (await worker._run())["status"] == "skipped"
    assert conn.query is None and conn.closed


@pytest.mark.asyncio
async def test_candidates_require_premium_flag_and_timezone(monkeypatch):
    conn = _Conn(rows=[
        {"id": uuid4(), "company_id": uuid4(), "timezone": "America/Los_Angeles",
         "enabled_features": {"employee_schedule": True}, "signup_source": None},
        {"id": uuid4(), "company_id": uuid4(), "timezone": None,
         "enabled_features": {"employee_schedule": True, "schedule_autopilot": True},
         "signup_source": None},
    ])
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(worker, "scheduler_settings_row", AsyncMock(return_value={
        "enabled": True, "max_per_cycle": 50,
    }))
    coords = AsyncMock(side_effect=AssertionError("no weather call expected"))
    monkeypatch.setattr(worker, "ensure_location_coordinates", coords)

    result = await worker._run()

    assert result["feature_disabled"] == 1
    assert result["no_timezone"] == 1
    assert result["processed"] == 0
    assert "schedule_autopilot" in conn.query
    coords.assert_not_awaited()
    assert conn.closed


@pytest.mark.asyncio
async def test_sweep_orders_stalest_first_and_counts_each_outcome(monkeypatch):
    def row(tz="America/Los_Angeles"):
        return {"id": uuid4(), "company_id": uuid4(), "timezone": tz,
                "enabled_features": {"employee_schedule": True, "schedule_autopilot": True},
                "signup_source": None}

    rows = [row(), row(), row(), row("Not/AZone")]
    conn = _Conn(rows=rows)
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(worker, "scheduler_settings_row", AsyncMock(return_value={
        "enabled": True, "max_per_cycle": 50,
    }))
    # Row 0 has no coordinates, row 1's fetch fails, row 2 succeeds.
    monkeypatch.setattr(worker, "ensure_location_coordinates", AsyncMock(
        side_effect=[None, (37.0, -122.0), (37.0, -122.0)],
    ))
    monkeypatch.setattr(worker, "fetch_daily_forecast", AsyncMock(side_effect=[None, [{"x": 1}]]))
    upsert = AsyncMock(return_value=3)
    monkeypatch.setattr(worker, "upsert_weather_days", upsert)

    result = await worker._run()

    assert "NULLS FIRST" in conn.query
    assert result["no_coordinates"] == 1
    assert result["fetch_failed"] == 1
    assert result["no_timezone"] == 1
    assert (result["processed"], result["written"]) == (1, 3)
    assert upsert.await_args.kwargs["location_id"] == rows[2]["id"]


@pytest.mark.asyncio
async def test_forced_sweep_bypasses_gate_and_claim(monkeypatch):
    class ForcedConn(_Conn):
        def __init__(self):
            super().__init__(claimed=False)
            self.executed = []

        async def execute(self, query, *_args):
            self.executed.append(query)

    conn = ForcedConn()
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(worker, "scheduler_settings_row", AsyncMock(return_value=None))

    result = await worker._run(force=True)

    assert result["status"] == "ok" and result["candidates"] == 0
    assert "last_run_at=NOW()" in conn.executed[0]
