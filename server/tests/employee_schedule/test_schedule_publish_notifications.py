"""Publishing stages employee deliveries before commit and wakes the worker after."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.models.scheduling.employee_schedule import PublishRange
from app.matcha.routes.employee_schedule import shifts as routes


@pytest.mark.asyncio
@pytest.mark.parametrize("was_published", [False, True])
async def test_single_publish_only_notifies_on_first_publish(monkeypatch, was_published):
    company_id, shift_id = uuid4(), uuid4()
    events = []

    class Conn:
        @asynccontextmanager
        async def transaction(self):
            events.append("begin")
            yield self
            events.append("commit")

        async def fetchrow(self, query, *_args):
            if "SELECT id, status" in query:
                return {"id": shift_id, "status": "published" if was_published else "draft",
                        "location_id": None}
            if "UPDATE schedule_shifts" in query:
                return {"id": shift_id}
            raise AssertionError(query)

    @asynccontextmanager
    async def connection():
        yield Conn()

    async def noop(*_args, **_kwargs):
        return None

    async def stage(*_args, **kwargs):
        assert events[-1] == "begin"
        assert kwargs["shift_ids"] == [shift_id]
        events.append("stage")
        return 1

    monkeypatch.setattr(routes, "get_connection", connection)
    monkeypatch.setattr(routes, "require_company_id", lambda _user: company(company_id))
    monkeypatch.setattr(routes, "assert_schedule_location_ready_to_publish", noop)
    monkeypatch.setattr(routes, "_lock_and_assert_publish_assignments_eligible", noop)
    monkeypatch.setattr(routes, "log_audit", noop)
    monkeypatch.setattr(routes, "reconcile_warning_events", noop)
    monkeypatch.setattr(routes, "fetch_shift_by_id", lambda *_args: shift_result(shift_id))
    monkeypatch.setattr(routes, "stage_publish_events", stage)
    monkeypatch.setattr(routes, "dispatch_events", lambda: events.append("dispatch"))

    await routes.publish_shift(shift_id, SimpleNamespace(id=uuid4()))
    if was_published:
        assert events == ["begin", "commit"]
    else:
        assert events == ["begin", "stage", "commit", "dispatch"]


@pytest.mark.asyncio
@pytest.mark.parametrize("has_drafts", [False, True])
async def test_range_publish_batches_one_delivery_per_employee(monkeypatch, has_drafts):
    company_id, shift_id = uuid4(), uuid4()
    events = []
    now = datetime.now(timezone.utc)

    class Conn:
        @asynccontextmanager
        async def transaction(self):
            events.append("begin")
            yield self
            events.append("commit")

        async def fetch(self, query, *_args):
            assert "status = 'draft'" in query
            return [{"id": shift_id, "location_id": None}] if has_drafts else []

        async def fetchval(self, query, *_args):
            assert "WITH updated" in query
            return 1

    @asynccontextmanager
    async def connection():
        yield Conn()

    async def noop(*_args, **_kwargs):
        return None

    async def stage(*_args, **kwargs):
        assert events[-1] == "begin"
        assert kwargs["shift_ids"] == [shift_id]
        events.append("stage")
        return 1

    async def fetch_shifts(*_args, **_kwargs):
        return []

    monkeypatch.setattr(routes, "get_connection", connection)
    monkeypatch.setattr(routes, "require_company_id", lambda _user: company(company_id))
    monkeypatch.setattr(routes, "assert_location_in_company", noop)
    monkeypatch.setattr(routes, "assert_schedule_location_ready_to_publish", noop)
    monkeypatch.setattr(routes, "_lock_and_assert_publish_assignments_eligible", noop)
    monkeypatch.setattr(routes, "log_audit", noop)
    monkeypatch.setattr(routes, "reconcile_warning_events", noop)
    monkeypatch.setattr(routes, "fetch_shifts", fetch_shifts)
    monkeypatch.setattr(routes, "stage_publish_events", stage)
    monkeypatch.setattr(routes, "dispatch_events", lambda: events.append("dispatch"))

    result = await routes.publish_range(
        PublishRange(start=now, end=now + timedelta(days=7)), SimpleNamespace(id=uuid4()),
    )
    assert result["published"] == int(has_drafts)
    if has_drafts:
        assert events == ["begin", "stage", "commit", "dispatch"]
    else:
        assert events == ["begin", "commit"]


async def company(value):
    return value


async def shift_result(shift_id):
    return {"id": str(shift_id)}
