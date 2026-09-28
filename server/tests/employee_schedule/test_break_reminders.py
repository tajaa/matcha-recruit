"""Break-start push reminders + their sweep cadence (no DB, no real APNs)."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.services.apns_service import PushResult
from app.matcha.services.scheduling import break_reminders as reminders

PACIFIC = "America/Los_Angeles"
# 2026-09-23 is PDT (UTC-7): a noon Pacific break is 19:00 UTC.
NOON_PT = datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc)


def _row(*, planned=None, timezone_name=PACIFIC, user_id="user"):
    return {
        "assignment_id": uuid4(), "shift_id": uuid4(), "company_id": uuid4(),
        "location_id": uuid4(), "location_name": "Downtown", "timezone": timezone_name,
        "employee_id": uuid4(), "user_id": uuid4() if user_id == "user" else user_id,
        "employee_name": "Ana Ruiz",
        "planned_breaks": planned if planned is not None else [
            {"kind": "meal", "ordinal": 1, "start_local": "2026-09-23T12:00:00",
             "duration_minutes": 30, "source": "manager"},
        ],
    }


def _at(hour, minute):
    return datetime(2026, 9, 23, hour, minute, tzinfo=timezone.utc)


@pytest.mark.parametrize("now,due", [
    (_at(18, 56), False),  # 11:56 PT — more than LEAD early
    (_at(18, 57), True),   # 11:57 PT — LEAD boundary
    (NOON_PT, True),
    (_at(19, 10), True),   # 12:10 PT — GRACE boundary
    (_at(19, 11), False),  # too late to be useful; never sent
    (_at(12, 0), False),   # noon UTC is 5 AM PT: must not read the wall clock as UTC
])
def test_due_is_judged_on_the_location_wall_clock(now, due):
    assert bool(reminders.due_breaks([_row()], now=now)) is due


def test_offset_on_start_local_is_ignored_for_the_clock_face():
    planned = [{"kind": "rest", "ordinal": 2, "start_local": "2026-09-23T12:00:00-07:00", "duration_minutes": 10}]
    [item] = reminders.due_breaks([_row(planned=planned)], now=NOON_PT)
    assert item.start_local == datetime(2026, 9, 23, 12, 0)
    assert item.dedupe_key.endswith(":rest:2:2026-09-23T12:00")


def test_bad_timezone_falls_back_to_utc_and_malformed_entries_are_skipped():
    planned = [
        {"kind": "meal", "ordinal": 1, "start_local": "2026-09-23T19:00:00", "duration_minutes": 30},
        {"kind": "nap", "ordinal": 1, "start_local": "2026-09-23T19:00:00", "duration_minutes": 30},
        {"kind": "rest", "ordinal": "x", "start_local": "2026-09-23T19:00:00", "duration_minutes": 10},
        {"kind": "rest", "ordinal": 2, "start_local": "not a time", "duration_minutes": 10},
        "garbage",
    ]
    due = reminders.due_breaks([_row(planned=planned, timezone_name="Mars/Olympus")], now=NOON_PT)
    assert [(item.kind, item.ordinal) for item in due] == [("meal", 1)]
    assert reminders.due_breaks([_row(planned='[{"kind": "meal"}]')], now=NOON_PT) == []


def test_a_retimed_break_gets_its_own_dedupe_key():
    [first] = reminders.due_breaks([_row()], now=NOON_PT)
    moved = _row(planned=[{"kind": "meal", "ordinal": 1, "start_local": "2026-09-23T12:05:00", "duration_minutes": 30}])
    moved["assignment_id"] = first.assignment_id
    [second] = reminders.due_breaks([moved], now=_at(19, 3))
    assert first.dedupe_key != second.dedupe_key


def test_push_copy_states_the_scheduled_time_not_an_instruction():
    [item] = reminders.due_breaks([_row()], now=NOON_PT)
    assert reminders.push_message(item) == ("Meal break", "Your 30-minute meal break is scheduled for 12:00 PM.")


# ── One send ─────────────────────────────────────────────────────────────────


class _Tx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.depth += 1

    async def __aexit__(self, exc_type, *_):
        self.conn.depth -= 1
        if exc_type is not None:
            self.conn.rolled_back += 1
        return False


class _Conn:
    def __init__(self, *, locked=True, existing=False, recorded_keys=(), rows=()):
        self.locked = locked
        self.existing = existing
        self.recorded_keys = list(recorded_keys)
        self.rows = list(rows)
        self.depth = 0
        self.rolled_back = 0
        self.inserts = []

    def transaction(self):
        return _Tx(self)

    async def fetchval(self, query, *params):
        if "pg_try_advisory_xact_lock" in query:
            return self.locked
        if "SELECT 1 FROM schedule_break_reminder_events" in query:
            return self.existing
        if "INSERT INTO schedule_break_reminder_events" in query:
            assert self.depth >= 1, "the record must be written inside the send transaction"
            self.inserts.append(params)
            return uuid4()
        raise AssertionError(query)

    async def fetch(self, query, *params):
        if "FROM schedule_shift_assignments" in query:
            return self.rows
        if "SELECT dedupe_key" in query:
            return [{"dedupe_key": key} for key in self.recorded_keys if key in params[0]]
        raise AssertionError(query)


def _item(**row_overrides):
    [item] = reminders.due_breaks([{**_row(), **row_overrides}], now=NOON_PT)
    return item


def _push(monkeypatch, *, configured=True, result=None, error=None):
    sent = []

    async def send_to_user(user_id, title, body, payload, *, kind, conn):
        sent.append({"user_id": user_id, "title": title, "body": body, "payload": payload, "kind": kind})
        if error:
            raise error
        return result or PushResult(sent=1)

    monkeypatch.setattr(reminders.apns_service, "is_configured", lambda: configured)
    monkeypatch.setattr(reminders.apns_service, "send_to_user", send_to_user)
    return sent


def _recorded(conn) -> dict:
    [params] = conn.inserts
    names = (
        "company_id event_date channel reminder_type recipient_type recipient recipient_user_id "
        "employee_id employee_name covered_employee_ids location_id location_name location_timezone "
        "shift_id assignment_id break_kind break_start_local break_duration_minutes context outcome "
        "outcome_detail dedupe_key"
    ).split()
    return dict(zip(names, params))


@pytest.mark.asyncio
async def test_accepted_push_is_recorded_with_employee_location_and_break(monkeypatch):
    sent = _push(monkeypatch, result=PushResult(sent=2))
    conn = _Conn()
    item = _item()

    outcome = await reminders.send_break_reminder(conn, item, now=_at(18, 58))

    assert outcome == "accepted"
    assert sent[0]["kind"] == "schedule_break_reminder"
    assert sent[0]["payload"]["link"] == "matchaschedule://schedule"
    row = _recorded(conn)
    assert (row["channel"], row["reminder_type"], row["recipient_type"]) == ("push", "break_start", "employee")
    assert row["company_id"] == item.company_id and row["employee_id"] == item.employee_id
    assert row["location_id"] == item.location_id and row["location_timezone"] == PACIFIC
    assert row["break_kind"] == "meal" and row["break_start_local"] == datetime(2026, 9, 23, 12, 0)
    assert row["event_date"].isoformat() == "2026-09-23"
    assert row["outcome"] == "accepted" and "2 device(s)" in row["outcome_detail"]
    assert row["dedupe_key"] == item.dedupe_key
    assert '"sent_minutes_before_start": 2.0' in row["context"]


@pytest.mark.parametrize("setup,outcome,detail", [
    ({"result": PushResult(transient=1)}, "failed", "did not accept it for 1 device(s)"),
    ({"result": PushResult(dead=["tok"])}, "failed", "no longer valid"),
    ({"error": RuntimeError("token lookup failed")}, "failed", "RuntimeError: token lookup failed"),
    ({"result": PushResult()}, "unavailable", "No Matcha Schedule device registered"),
    ({"configured": False}, "unavailable", "Push notifications are not configured"),
])
@pytest.mark.asyncio
async def test_failed_and_unavailable_pushes_are_recorded_not_dropped(monkeypatch, setup, outcome, detail):
    _push(monkeypatch, **setup)
    conn = _Conn()

    assert await reminders.send_break_reminder(conn, _item(), now=NOON_PT) == outcome

    row = _recorded(conn)
    assert row["outcome"] == outcome and detail in row["outcome_detail"]
    if "error" in setup:
        # The failed token query ran in a savepoint; the record still landed.
        assert conn.rolled_back == 1


@pytest.mark.asyncio
async def test_employee_without_an_app_account_is_unavailable_without_a_send(monkeypatch):
    sent = _push(monkeypatch)
    conn = _Conn()
    assert await reminders.send_break_reminder(conn, _item(user_id=None), now=NOON_PT) == "unavailable"
    assert sent == []
    assert _recorded(conn)["outcome_detail"] == "Employee has no Matcha Schedule account"


@pytest.mark.parametrize("conn_kwargs", [{"locked": False}, {"existing": True}])
@pytest.mark.asyncio
async def test_a_break_already_claimed_or_recorded_is_never_pushed_twice(monkeypatch, conn_kwargs):
    sent = _push(monkeypatch)
    conn = _Conn(**conn_kwargs)
    assert await reminders.send_break_reminder(conn, _item(), now=NOON_PT) == "skipped"
    assert sent == [] and conn.inserts == []


@pytest.mark.asyncio
async def test_sweep_skips_recorded_breaks_caps_the_cycle_and_isolates_failures(monkeypatch):
    sent = _push(monkeypatch)
    rows = [_row() for _ in range(4)]
    recorded_key = reminders.due_breaks([rows[0]], now=NOON_PT)[0].dedupe_key
    conn = _Conn(rows=rows, recorded_keys=[recorded_key])

    real_send = reminders.send_break_reminder
    calls = []

    async def flaky(conn_arg, item, *, now):
        calls.append(item.assignment_id)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return await real_send(conn_arg, item, now=now)

    monkeypatch.setattr(reminders, "send_break_reminder", flaky)

    result = await reminders.send_due_break_reminders(conn, now=NOON_PT, limit=3)

    assert result == {"due": 3, "skipped": 1, "errors": 1, "accepted": 1}
    assert rows[3]["assignment_id"] not in calls  # over the cycle cap
    assert len(sent) == 1


# ── Sweep cadence (worker) ───────────────────────────────────────────────────


class _WorkerConn:
    def __init__(self, *, claimed):
        self.claimed = claimed
        self.closed = False
        self.claim_params = None

    async def fetchval(self, query, *params):
        assert "UPDATE scheduler_settings SET last_run_at = NOW()" in query
        self.claim_params = params
        return True if self.claimed else None

    async def close(self):
        self.closed = True


def _worker(monkeypatch, *, enabled=True, claimed=True, sweep_error=None):
    from app.workers.tasks import schedule_break_reminders as worker

    conn = _WorkerConn(claimed=claimed)
    rescheduled = []

    async def get_connection():
        return conn

    async def is_enabled(*args, **kwargs):
        return enabled

    async def settings(*args, **kwargs):
        return {"max_per_cycle": 50}

    async def sweep(conn_arg, *, limit):
        if sweep_error:
            raise sweep_error
        return {"due": 0, "limit_seen": limit}

    monkeypatch.setattr(worker, "get_db_connection", get_connection)
    monkeypatch.setattr(worker, "scheduler_enabled", is_enabled)
    monkeypatch.setattr(worker, "scheduler_settings_row", settings)
    monkeypatch.setattr(reminders, "send_due_break_reminders", sweep)
    monkeypatch.setattr(worker, "_reschedule", lambda countdown: rescheduled.append(countdown))
    return worker, conn, rescheduled


def test_live_chain_sweeps_and_re_enqueues(monkeypatch):
    worker, conn, rescheduled = _worker(monkeypatch)
    result = worker.run_schedule_break_reminders.run()
    assert result == {"due": 0, "limit_seen": 50}
    assert rescheduled == [reminders.SWEEP_SECONDS]
    assert conn.claim_params == ("schedule_break_reminders", int(reminders.SWEEP_SECONDS * 0.75))
    assert conn.closed


@pytest.mark.parametrize("kwargs,reason", [
    ({"enabled": False}, "disabled"),
    ({"claimed": False}, "another_chain"),
])
def test_disabled_or_duplicate_chain_ends_without_re_enqueueing(monkeypatch, kwargs, reason):
    worker, conn, rescheduled = _worker(monkeypatch, **kwargs)
    result = worker.run_schedule_break_reminders.run()
    assert result["reason"] == reason
    assert rescheduled == []
    assert conn.closed


def test_a_failed_sweep_keeps_the_cadence(monkeypatch):
    worker, _, rescheduled = _worker(monkeypatch, sweep_error=RuntimeError("db blip"))
    with pytest.raises(RuntimeError):
        worker.run_schedule_break_reminders.run()
    assert rescheduled == [reminders.SWEEP_SECONDS]


def test_sweep_is_registered_with_the_worker_dispatcher():
    source = (Path(__file__).parents[2] / "app/workers/celery_app.py").read_text()
    assert '"app.workers.tasks.schedule_break_reminders",' in source
    assert '("schedule_break_reminders", "app.workers.tasks.schedule_break_reminders", "run_schedule_break_reminders")' in source
