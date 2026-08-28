"""Automatic weekly schedule proposal cadence and dispatch behavior."""

from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.workers.tasks import schedule_auto_generation as worker


class _Conn:
    def __init__(self, locations, active=False):
        self.locations = locations
        self.active = active
        self.closed = False

    async def fetch(self, *_args):
        return self.locations

    async def fetchval(self, *_args):
        return self.active

    async def close(self):
        self.closed = True


def test_upcoming_week_starts_on_next_sunday():
    assert worker.upcoming_week_start(date(2026, 8, 24)) == date(2026, 8, 30)
    assert worker.upcoming_week_start(date(2026, 8, 30)) == date(2026, 9, 6)


def test_feature_gate_requires_schedule_and_huume_workspace():
    enabled = {"employee_schedule": True, "huume": True, "matcha_work": True}
    assert worker.supports_automatic_generation(enabled, None) is True
    assert worker.supports_automatic_generation({**enabled, "huume": False}, None) is False


@pytest.mark.asyncio
async def test_worker_generates_one_review_only_proposal(monkeypatch):
    company_id, location_id = uuid4(), uuid4()
    conn = _Conn([{
        "company_id": company_id,
        "location_id": location_id,
        "timezone": "America/Los_Angeles",
        "enabled_features": {
            "employee_schedule": True, "huume": True, "matcha_work": True,
        },
        "signup_source": None,
    }])
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(
        worker, "scheduler_settings_row",
        AsyncMock(return_value={"enabled": True, "max_per_cycle": 100}),
    )
    propose = AsyncMock(return_value={"status": "ready", "generation_run_id": str(uuid4())})
    monkeypatch.setattr(
        "app.matcha.services.scheduling.week_builder.propose_week_draft", propose,
    )

    result = await worker._run()

    assert result["generated"] == 1
    propose.assert_awaited_once()
    kwargs = propose.await_args.kwargs
    assert kwargs["origin"] == "automatic"
    assert kwargs["actor_user_id"] is None
    assert kwargs["thread_id"] is None
    assert kwargs["source_mode"] == "auto"
    assert kwargs["week_start"].weekday() == 6
    assert conn.closed is True


@pytest.mark.asyncio
async def test_worker_skips_scope_with_existing_proposal(monkeypatch):
    conn = _Conn([{
        "company_id": uuid4(),
        "location_id": uuid4(),
        "timezone": "UTC",
        "enabled_features": {
            "employee_schedule": True, "huume": True, "matcha_work": True,
        },
        "signup_source": None,
    }], active=True)
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(
        worker, "scheduler_settings_row",
        AsyncMock(return_value={"enabled": True, "max_per_cycle": 100}),
    )
    propose = AsyncMock()
    monkeypatch.setattr(
        "app.matcha.services.scheduling.week_builder.propose_week_draft", propose,
    )

    result = await worker._run()

    assert result["already_present"] == 1
    propose.assert_not_awaited()
