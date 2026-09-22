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
