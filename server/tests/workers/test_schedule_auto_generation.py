"""Tenant-configured schedule automation timing and execution."""

from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import schedule_automation, week_builder
from app.matcha.services.scheduling.schedule_automation import next_run_at, target_week_start
from app.workers.tasks import schedule_auto_generation as worker


class _Conn:
    def __init__(self, rule):
        self.rule = rule
        self.closed = False
        self.execute_calls = []

    async def fetchrow(self, *_args):
        return self.rule

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "UPDATE 1"

    async def close(self):
        self.closed = True


class _AsyncContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SuggestionConn:
    def __init__(self):
        self.stale_query = None
        self.existing_query = None

    async def execute(self, query, *args):
        if "SET status='stale'" in query:
            self.stale_query = (query, args)
            return "UPDATE 1"
        raise AssertionError(f"unexpected execute query: {query}")

    async def fetchrow(self, query, *_args):
        if "FROM schedule_generation_runs" in query:
            self.existing_query = query
            return None
        raise AssertionError(f"unexpected fetchrow query: {query}")


def test_weekly_next_run_uses_location_wall_clock():
    after = datetime(2026, 8, 24, 20, tzinfo=timezone.utc)  # Monday afternoon LA
    result = next_run_at(
        cadence="weekly",
        timezone_name="America/Los_Angeles",
        run_time=time(9),
        run_weekday=4,  # Thursday in the product's Sunday=0 convention
        after=after,
    )
    assert result == datetime(2026, 8, 27, 16, tzinfo=timezone.utc)


def test_weekly_target_is_relative_to_the_scheduled_occurrence():
    result = target_week_start(
        cadence="weekly",
        scheduled_for=datetime(2026, 8, 27, 16, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
        target_weeks_ahead=2,
        one_time_week_start=None,
    )
    assert result == date(2026, 9, 6)


@pytest.mark.asyncio
async def test_rule_generates_review_proposal_and_queues_only_its_next_occurrence(monkeypatch):
    company_id, location_id, rule_id, template_id = uuid4(), uuid4(), uuid4(), uuid4()
    scheduled_for = datetime(2026, 8, 27, 16, tzinfo=timezone.utc)
    conn = _Conn({
        "id": rule_id,
        "company_id": company_id,
        "location_id": location_id,
        "week_template_id": template_id,
        "enabled": True,
        "cadence": "weekly",
        "run_weekday": 4,
        "run_time": time(9),
        "target_weeks_ahead": 1,
        "target_week_start": None,
        "next_run_at": scheduled_for,
        "schedule_version": 3,
        "timezone": "America/Los_Angeles",
        "enabled_features": {"employee_schedule": True, "huume": True, "matcha_work": True},
        "signup_source": None,
        "company_status": "approved",
    })
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    generation_id = uuid4()
    generate = AsyncMock(return_value={
        "status": "generated", "message": "Ready", "generation_run_id": str(generation_id),
    })
    monkeypatch.setattr(worker, "generate_review_suggestion", generate)
    enqueue = Mock()
    monkeypatch.setattr(worker, "enqueue_schedule_automation", enqueue)

    result = await worker._run(str(rule_id), 3, scheduled_for.isoformat())

    assert result["status"] == "generated"
    assert result["week_start"] == "2026-08-30"
    generate.assert_awaited_once_with(
        company_id=company_id,
        location_id=location_id,
        week_start=date(2026, 8, 30),
        week_template_id=template_id,
    )
    enqueue.assert_called_once()
    assert enqueue.call_args.args[:2] == (rule_id, 3)
    assert conn.closed is True


@pytest.mark.asyncio
async def test_stale_queued_version_is_a_noop(monkeypatch):
    rule_id = uuid4()
    scheduled_for = datetime(2026, 8, 27, 16, tzinfo=timezone.utc)
    conn = _Conn({
        "id": rule_id,
        "enabled": True,
        "schedule_version": 4,
        "next_run_at": scheduled_for,
    })
    monkeypatch.setattr(worker, "get_db_connection", AsyncMock(return_value=conn))
    generate = AsyncMock()
    monkeypatch.setattr(worker, "generate_review_suggestion", generate)

    result = await worker._run(str(rule_id), 3, scheduled_for.isoformat())

    assert result == {"skipped": True, "reason": "stale_or_disabled_rule"}
    generate.assert_not_awaited()
    assert conn.execute_calls == []
    assert conn.closed is True


@pytest.mark.asyncio
async def test_removed_applied_week_does_not_block_replacement_suggestion(monkeypatch):
    company_id, location_id, template_id = uuid4(), uuid4(), uuid4()
    conn = _SuggestionConn()
    monkeypatch.setattr(schedule_automation, "connection_or_direct", lambda: _AsyncContext(conn))
    monkeypatch.setattr(
        week_builder,
        "get_week_build_readiness",
        AsyncMock(return_value={"status": "ok", "ready": True}),
    )
    generation_id = uuid4()
    monkeypatch.setattr(
        week_builder,
        "propose_week_draft",
        AsyncMock(return_value={"status": "ready", "generation_run_id": str(generation_id)}),
    )

    result = await schedule_automation.generate_review_suggestion(
        company_id=company_id,
        location_id=location_id,
        week_start=date(2026, 8, 30),
        week_template_id=template_id,
    )

    assert result == {
        "status": "generated",
        "message": "Huume prepared a schedule suggestion for manager review.",
        "generation_run_id": str(generation_id),
    }
    assert conn.stale_query is not None
    assert conn.stale_query[1][-2:] == (
        datetime(2026, 8, 30, tzinfo=timezone.utc),
        datetime(2026, 9, 6, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_cancelled_automatic_suggestion_does_not_block_replacement(monkeypatch):
    company_id, location_id, template_id = uuid4(), uuid4(), uuid4()
    conn = _SuggestionConn()
    monkeypatch.setattr(schedule_automation, "connection_or_direct", lambda: _AsyncContext(conn))
    monkeypatch.setattr(
        week_builder,
        "get_week_build_readiness",
        AsyncMock(return_value={"status": "ok", "ready": True}),
    )
    generation_id = uuid4()
    monkeypatch.setattr(
        week_builder,
        "propose_week_draft",
        AsyncMock(return_value={"status": "ready", "generation_run_id": str(generation_id)}),
    )

    result = await schedule_automation.generate_review_suggestion(
        company_id=company_id,
        location_id=location_id,
        week_start=date(2026, 8, 30),
        week_template_id=template_id,
    )

    assert result["status"] == "generated"
    assert "status IN ('proposed', 'applied')" in conn.existing_query
    assert "cancelled" not in conn.existing_query
