"""Durable schedule bell and push delivery without a live database."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import employee_schedule_notifications as notifications


@pytest.mark.parametrize("event_type,payload", [
    ("schedule_offer_received", {"request_id": "request-1", "starts_at": "2026-09-27T06:30:00+00:00"}),
    ("schedule_request_accepted", {"request_id": "request-1", "starts_at": "2026-09-27T06:30:00+00:00"}),
    ("schedule_request_withdrawn", {"request_id": "request-1", "starts_at": "2026-09-27T06:30:00+00:00"}),
    ("schedule_request_decided", {"request_id": "request-1", "decision": "approved", "starts_at": "2026-09-27T06:30:00+00:00"}),
    ("schedule_published", {"batch_id": "batch-1", "shift_count": 2, "starts_at": "2026-09-27T06:30:00+00:00"}),
])
@pytest.mark.asyncio
async def test_event_creates_one_bell_and_push_even_if_retried(monkeypatch, event_type, payload):
    delivery_id, company_id, user_id = (uuid4() for _ in range(3))
    pushes = []

    class Conn:
        sent = False
        bell_count = 0

        @asynccontextmanager
        async def transaction(self):
            yield self

        async def fetchrow(self, query, *_args):
            assert "FOR UPDATE SKIP LOCKED" in query
            if self.sent:
                return None
            return {"id": delivery_id, "company_id": company_id,
                    "recipient_user_id": user_id, "event_type": event_type,
                    "dedupe_key": "key", "payload": payload}

        async def execute(self, query, *_args):
            if "INSERT INTO mw_notifications" in query:
                self.bell_count += 1
            if "SET sent_at=NOW()" in query:
                self.sent = True

    async def push(*args, **kwargs):
        pushes.append((args, kwargs))

    monkeypatch.setattr(notifications.apns_service, "send_to_user", push)
    conn = Conn()
    assert await notifications.deliver_one(conn, delivery_id) is True
    assert await notifications.deliver_one(conn, delivery_id) is False
    assert conn.bell_count == 1
    assert len(pushes) == 1
    assert pushes[0][1]["kind"] == event_type
    assert "Sun Sep 27, 6:30 AM" in pushes[0][0][2]


@pytest.mark.asyncio
async def test_request_event_stages_recipients_with_the_request_snapshot():
    company_id, request_id, shift_id, employee_id, user_id = (uuid4() for _ in range(5))
    inserts = []

    class Conn:
        async def fetchrow(self, *_args):
            return {"shift_id": shift_id, "starts_at": datetime(2026, 9, 27, 6, 30, tzinfo=timezone.utc),
                    "role": "Barista"}

        async def fetch(self, query, *_args):
            assert "org_id=$1" in query
            return [{"user_id": user_id}]

        async def execute(self, query, *args):
            assert "ON CONFLICT" in query
            inserts.append(args)

    count = await notifications.stage_request_event(
        Conn(), company_id=company_id, request_id=request_id,
        event_type="schedule_offer_received", recipient_employee_ids=[employee_id],
        dedupe_key=str(request_id),
    )
    assert count == 1
    assert inserts[0][:4] == (company_id, user_id, "schedule_offer_received", str(request_id))
    assert '"starts_at": "2026-09-27T06:30:00+00:00"' in inserts[0][4]


@pytest.mark.asyncio
async def test_publish_stages_one_delivery_per_employee_in_batch():
    company_id, batch_id, shift_id, user_id = (uuid4() for _ in range(4))
    inserts = []

    class Conn:
        async def fetch(self, query, *_args):
            assert "GROUP BY e.user_id" in query
            return [{"user_id": user_id, "shift_count": 2,
                     "first_starts_at": datetime(2026, 9, 27, 6, 30, tzinfo=timezone.utc)}]

        async def execute(self, _query, *args):
            inserts.append(args)

    count = await notifications.stage_publish_events(
        Conn(), company_id=company_id, shift_ids=[shift_id], batch_id=batch_id,
    )
    assert count == 1
    assert inserts[0][:3] == (company_id, user_id, str(batch_id))


@pytest.mark.asyncio
async def test_failed_delivery_does_not_block_later_rows(monkeypatch):
    first, second = uuid4(), uuid4()
    seen = []

    failures = []

    class Conn:
        async def fetch(self, query, *_args):
            assert "failed_at IS NULL" in query
            return [{"id": first}, {"id": second}]

        async def execute(self, query, *args):
            assert "attempts = attempts + 1" in query
            failures.append(args)

    async def deliver(_conn, delivery_id):
        seen.append(delivery_id)
        if delivery_id == first:
            raise RuntimeError("push temporarily unavailable")
        return True

    monkeypatch.setattr(notifications, "deliver_one", deliver)
    with pytest.raises(RuntimeError, match="push temporarily unavailable"):
        await notifications.deliver_pending(Conn())
    assert seen == [first, second]
    # Transient: counted, parked only once attempts reach the cap.
    assert failures == [(first, notifications.MAX_DELIVERY_ATTEMPTS, False)]


@pytest.mark.asyncio
async def test_unrenderable_delivery_is_parked_on_first_failure(monkeypatch):
    """An unknown event type can never succeed; without parking it the sweep
    would raise on it forever and hold every retry behind it."""
    dead = uuid4()
    failures = []

    class Conn:
        async def fetch(self, *_args):
            return [{"id": dead}]

        async def execute(self, query, *args):
            failures.append(args)

    async def deliver(_conn, _delivery_id):
        raise ValueError("Unknown schedule notification event: bogus")

    monkeypatch.setattr(notifications, "deliver_one", deliver)
    with pytest.raises(ValueError):
        await notifications.deliver_pending(Conn())
    assert failures == [(dead, notifications.MAX_DELIVERY_ATTEMPTS, True)]


@pytest.mark.asyncio
async def test_recovery_sends_pending_rows_then_finds_nothing(monkeypatch):
    company_id, user_id, delivery_id = (uuid4() for _ in range(3))
    pushes = []

    class Conn:
        sent = False

        @asynccontextmanager
        async def transaction(self):
            yield self

        async def fetch(self, *_args):
            return [] if self.sent else [{"id": delivery_id}]

        async def fetchrow(self, *_args):
            return {"id": delivery_id, "company_id": company_id,
                    "recipient_user_id": user_id, "event_type": "schedule_published",
                    "dedupe_key": "batch", "payload": json.dumps({"shift_count": 1})}

        async def execute(self, query, *_args):
            if "SET sent_at=NOW()" in query:
                self.sent = True

    async def push(*_args, **_kwargs):
        pushes.append(1)

    monkeypatch.setattr(notifications.apns_service, "send_to_user", push)
    conn = Conn()
    assert await notifications.deliver_pending(conn) == {"sent": 1, "pending": 1}
    assert await notifications.deliver_pending(conn) == {"sent": 0, "pending": 0}
    assert pushes == [1]


@pytest.mark.asyncio
async def test_empty_and_missing_request_events_do_not_stage_rows():
    company_id, request_id, employee_id = (uuid4() for _ in range(3))

    class Conn:
        async def fetchrow(self, *_args):
            return None

    conn = Conn()
    assert await notifications.stage_request_event(
        conn, company_id=company_id, request_id=request_id,
        event_type="schedule_offer_received", recipient_employee_ids=[], dedupe_key=str(request_id),
    ) == 0
    assert await notifications.stage_request_event(
        conn, company_id=company_id, request_id=request_id,
        event_type="schedule_offer_received", recipient_employee_ids=[employee_id], dedupe_key=str(request_id),
    ) == 0
    assert await notifications.stage_publish_events(
        conn, company_id=company_id, shift_ids=[], batch_id=uuid4(),
    ) == 0


def test_wall_time_handles_missing_and_unknown_events():
    assert notifications.wall_time(None) is None
    assert notifications.wall_time(datetime(2026, 9, 27, 6, 30)) == "Sun Sep 27, 6:30 AM"
    with pytest.raises(ValueError, match="Unknown schedule notification event"):
        notifications._render("schedule_unknown", {})


def test_dispatch_is_best_effort(monkeypatch):
    from app.workers.tasks import schedule_employee_notifications as worker
    calls = []
    monkeypatch.setattr(worker.send_schedule_employee_notifications, "delay", lambda: calls.append(1))
    notifications.dispatch_events()
    assert calls == [1]

    def broker_down():
        raise RuntimeError("broker down")

    monkeypatch.setattr(worker.send_schedule_employee_notifications, "delay", broker_down)
    notifications.dispatch_events()


@pytest.mark.asyncio
async def test_worker_uses_a_raw_connection_and_closes_it(monkeypatch):
    from app.workers.tasks import schedule_employee_notifications as worker
    events = []

    class Conn:
        async def close(self):
            events.append("close")

    async def get_conn():
        events.append("open")
        return Conn()

    async def deliver(_conn):
        events.append("deliver")
        return {"sent": 1, "pending": 1}

    monkeypatch.setattr(worker, "get_db_connection", get_conn)
    monkeypatch.setattr(worker, "deliver_pending", deliver)
    assert await worker._deliver() == {"sent": 1, "pending": 1}
    assert events == ["open", "deliver", "close"]


def test_send_and_recovery_tasks_run_the_same_delivery_sweep(monkeypatch):
    from app.workers.tasks import schedule_employee_notifications as worker
    calls = []

    async def deliver():
        calls.append(1)
        return {"sent": 1, "pending": 1}

    monkeypatch.setattr(worker, "_deliver", deliver)
    assert worker.send_schedule_employee_notifications.run()["sent"] == 1
    assert worker.recover_schedule_employee_notifications.run()["sent"] == 1
    assert calls == [1, 1]
