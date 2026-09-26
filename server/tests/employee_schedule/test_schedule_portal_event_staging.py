"""Portal requests stage recipient events before committing the request."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.matcha.models.scheduling.employee_schedule import CounterpartyAccept, ScheduleRequestCreate
from app.matcha.routes.employee_portal import schedule as portal


@pytest.mark.asyncio
async def test_targeted_swap_stages_offer_before_commit_and_dispatches_after(monkeypatch):
    company_id, employee_id, target_id, shift_id, counter_id, request_id = (uuid4() for _ in range(6))
    events = []

    class Conn:
        @asynccontextmanager
        async def transaction(self):
            events.append("begin")
            yield self
            events.append("commit")

        async def fetchrow(self, query, *_args):
            if "SELECT s.status" in query:
                return {"status": "published"}
            if "FROM employees WHERE id" in query:
                return {"employment_status": "active"}
            if "FROM schedule_requests r" in query:
                return {"id": request_id, "status": "awaiting_counterparty"}
            raise AssertionError(query)

        async def fetchval(self, query, *_args):
            assert "INSERT INTO schedule_requests" in query
            events.append("insert")
            return request_id

    @asynccontextmanager
    async def connection():
        yield Conn()

    async def audit(*_args, **_kwargs):
        events.append("audit")

    async def stage(*_args, **kwargs):
        assert events[-1] == "audit"
        assert kwargs["recipient_employee_ids"] == [target_id]
        assert kwargs["event_type"] == "schedule_offer_received"
        events.append("stage")
        return 1

    monkeypatch.setattr(portal, "get_connection", connection)
    monkeypatch.setattr(portal, "dispatch_events", lambda: events.append("dispatch"), raising=False)
    monkeypatch.setattr(
        "app.matcha.routes.employee_schedule._shared.serialize_request", lambda row: row,
    )
    monkeypatch.setattr("app.matcha.routes.employee_schedule._shared.log_audit", audit)
    monkeypatch.setattr(
        "app.matcha.services.scheduling.employee_schedule_notifications.stage_request_event", stage,
    )
    monkeypatch.setattr(
        "app.matcha.services.scheduling.employee_schedule_notifications.dispatch_events",
        lambda: events.append("dispatch"),
    )

    result = await portal.create_my_schedule_request(
        ScheduleRequestCreate(
            request_type="swap", shift_id=shift_id, target_employee_id=target_id,
            counter_shift_id=counter_id,
        ),
        {"id": employee_id, "org_id": company_id},
    )
    assert result["status"] == "awaiting_counterparty"
    assert events == ["begin", "insert", "audit", "stage", "commit", "dispatch"]


@pytest.mark.asyncio
async def test_acceptance_notifies_requester_after_commit(monkeypatch):
    company_id, owner_id, accepter_id, shift_id, request_id = (uuid4() for _ in range(5))
    events = []

    class Conn:
        @asynccontextmanager
        async def transaction(self):
            events.append("begin")
            yield self
            events.append("commit")

        async def fetchrow(self, query, *_args):
            if "FOR UPDATE" in query:
                return {"id": request_id, "employee_id": owner_id, "request_type": "pickup",
                        "shift_id": shift_id, "target_employee_id": None,
                        "counter_shift_id": None, "status": "awaiting_counterparty"}
            return {"status": "awaiting_manager"}

        async def fetchval(self, query, *_args):
            if "RETURNING" in query:
                # The state-changing UPDATE now RETURNs its transition stamp,
                # which becomes the notification dedupe nonce.
                events.append("update")
                from datetime import datetime, timezone
                return datetime.now(timezone.utc)
            return "active" if "employment_status" in query else 1

        async def execute(self, *_args):
            events.append("update")

    @asynccontextmanager
    async def connection():
        yield Conn()

    async def locked(_conn, _company, *_ids):
        from datetime import datetime, timezone
        return {str(shift_id): {"status": "published", "starts_at": datetime.now(timezone.utc)}}

    async def no_conflicts(*_args, **_kwargs):
        return []

    async def audit(*_args, **_kwargs):
        events.append("audit")

    async def stage(*_args, **kwargs):
        assert kwargs["recipient_employee_ids"] == [owner_id]
        assert kwargs["event_type"] == "schedule_request_accepted"
        # Keyed on the transition stamp, not the target state, so an
        # accept → withdraw → accept cycle notifies every time.
        assert kwargs["dedupe_key"].startswith(f"{request_id}:accepted:")
        assert not kwargs["dedupe_key"].endswith(":accepted:")
        events.append("stage")
        return 1

    from app.workers.tasks import schedule_request_notifications as manager_worker
    monkeypatch.setattr(portal, "get_connection", connection)
    monkeypatch.setattr("app.matcha.routes.employee_schedule._shared.fetch_locked_shift_pair", locked)
    monkeypatch.setattr("app.matcha.services.scheduling.shift_requests.find_same_day_assignments", no_conflicts)
    monkeypatch.setattr("app.matcha.routes.employee_schedule._shared.log_audit", audit)
    monkeypatch.setattr("app.matcha.routes.employee_schedule._shared.serialize_request", lambda row: row)
    monkeypatch.setattr("app.matcha.services.scheduling.employee_schedule_notifications.stage_request_event", stage)
    monkeypatch.setattr("app.matcha.services.scheduling.employee_schedule_notifications.dispatch_events", lambda: events.append("dispatch_employee"))
    monkeypatch.setattr(manager_worker.send_schedule_request_notifications, "delay", lambda *_args: events.append("dispatch_manager"))

    result = await portal.accept_schedule_request(
        request_id, CounterpartyAccept(), {"id": accepter_id, "org_id": company_id},
    )
    assert result["status"] == "awaiting_manager"
    assert events == ["begin", "update", "audit", "stage", "commit", "dispatch_manager", "dispatch_employee"]


@pytest.mark.asyncio
async def test_counterparty_withdrawal_notifies_requester(monkeypatch):
    company_id, owner_id, counterparty_id, request_id = (uuid4() for _ in range(4))
    events = []

    class Conn:
        @asynccontextmanager
        async def transaction(self):
            events.append("begin")
            yield self
            events.append("commit")

        async def fetchrow(self, *_args):
            return {"id": request_id, "employee_id": owner_id,
                    "target_employee_id": counterparty_id, "status": "awaiting_manager",
                    "request_type": "pickup"}

        async def execute(self, *_args):
            events.append("update")

        async def fetchval(self, query, *_args):
            # The state-changing UPDATE now RETURNs its transition stamp, which
            # becomes the notification dedupe nonce.
            assert "RETURNING" in query
            events.append("update")
            from datetime import datetime, timezone
            return datetime.now(timezone.utc)

    @asynccontextmanager
    async def connection():
        yield Conn()

    async def audit(*_args, **_kwargs):
        events.append("audit")

    async def resolved(*_args, **_kwargs):
        events.append("resolve_manager_alert")

    async def stage(*_args, **kwargs):
        assert kwargs["recipient_employee_ids"] == [owner_id]
        assert kwargs["event_type"] == "schedule_request_withdrawn"
        assert kwargs["dedupe_key"].startswith(f"{request_id}:withdrawn:")
        events.append("stage")
        return 1

    monkeypatch.setattr(portal, "get_connection", connection)
    monkeypatch.setattr("app.matcha.routes.employee_schedule._shared.log_audit", audit)
    monkeypatch.setattr("app.matcha.services.scheduling.schedule_request_notifications.mark_manager_ready_notifications_resolved", resolved)
    monkeypatch.setattr("app.matcha.services.scheduling.employee_schedule_notifications.stage_request_event", stage)
    monkeypatch.setattr("app.matcha.services.scheduling.employee_schedule_notifications.dispatch_events", lambda: events.append("dispatch"))

    result = await portal.withdraw_schedule_request(
        request_id, {"id": counterparty_id, "org_id": company_id},
    )
    assert result["status"] == "withdrawn"
    assert events == ["begin", "update", "resolve_manager_alert", "audit", "stage", "commit", "dispatch"]
