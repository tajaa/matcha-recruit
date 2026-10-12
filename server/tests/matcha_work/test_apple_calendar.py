from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

from app.matcha.models.matcha_work.calendar import AppleConnection, AppleSnapshot, AppleActionResult
from app.matcha.services.matcha_work import apple_calendar_service as apple
from app.matcha.routes.work import calendar as routes
from tests.agent_runtime.helpers import FakeConn, connection

USER, CONN = uuid4(), uuid4()
NOW = datetime.now(timezone.utc)
EVENT = {"id": "event", "calendar_id": "cal", "title": "Focus 🧋", "start": "2026-10-05", "end": "2026-10-06",
         "all_day": True, "notes": None, "location": None, "modified": "v1", "editable": True}


def row(**over):
    return {"user_id": USER, "connection_id": CONN, "calendars": [{"id": "cal", "title": "Home", "editable": True}],
            "destination": "cal", "snapshot": [EVENT], "window_start": datetime(2026, 9, 1, tzinfo=timezone.utc),
            "window_end": datetime(2027, 8, 1, tzinfo=timezone.utc), "synced_at": NOW, "complete": True, **over}


@pytest.fixture
def db(monkeypatch):
    fake = FakeConn().on("SELECT * FROM mw_apple_calendar_connections", row()).on("SELECT count(*)", 0)
    monkeypatch.setattr(apple, "connection_or_direct", connection(fake))
    return fake


def config(**over):
    return AppleConnection(user_id=USER, connection_id=CONN, calendars=[{"id": "cal", "title": "Home", "editable": True}], destination="cal", **over)


def snapshot(**over):
    return AppleSnapshot(connection_id=CONN, start="2026-09-01T00:00:00Z", end="2027-08-01T00:00:00Z",
                         events=[EVENT], **over)


@pytest.mark.asyncio
async def test_connect_and_disconnect_scope_and_cancel_pending_actions(db):
    await apple.connect(USER, config())
    args = db.ran("INSERT INTO mw_apple_calendar_connections")[0][2]
    assert args[:2] == (USER, CONN) and args[3] == "cal"
    assert "FOR UPDATE" not in db.ran("INSERT INTO mw_apple_calendar_connections")[0][1]
    await apple.disconnect(USER, CONN)
    assert db.ran("DELETE FROM mw_apple_calendar_connections")[0][2] == (USER, CONN)
    assert len(db.ran("status = 'cancelled'")) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("calendars,destination", [
    ([{"id": "cal", "title": "Home", "editable": False}], "cal"),
    ([{"id": "cal", "title": "Home", "editable": True}], "other"),
    ([{"id": "cal", "title": "Home", "editable": True}] * 2, "cal"),
])
async def test_connect_requires_unique_selected_calendars_and_a_writable_destination(db, calendars, destination):
    with pytest.raises(ValueError, match="writable destination"):
        await apple.connect(USER, AppleConnection(user_id=USER, connection_id=CONN, calendars=calendars, destination=destination))
    assert not db.calls


@pytest.mark.asyncio
async def test_snapshot_checks_the_connection_and_calendar_before_replacing_data(db):
    await apple.snapshot(USER, snapshot())
    assert "FOR UPDATE" in db.ran("SELECT *")[0][1]
    assert db.ran("SET snapshot")[0][2][:2] == (USER, CONN)
    db.on("SELECT *", None)
    with pytest.raises(HTTPException) as caught:
        await apple.snapshot(USER, snapshot())
    assert caught.value.status_code == 409
    db.on("SELECT *", row(calendars=[]))
    with pytest.raises(ValueError, match="did not select"):
        await apple.snapshot(USER, snapshot())


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [
    {"start": "2026-09-01"}, {"end": "2026-08-01T00:00:00Z"},
    {"end": "2028-08-01T00:00:00Z"}, {"events": [EVENT, EVENT]},
    {"events": [{**EVENT, "end": "2026-10-04"}]},
    {"events": [{**EVENT, "all_day": False}]},
    {"events": [{**EVENT, "end": "2026-10-06T00:00:00Z"}]},
])
async def test_invalid_snapshots_never_write(db, over):
    body = snapshot().model_copy(update=over)
    if "events" in over:
        from app.matcha.models.matcha_work.calendar import AppleEvent
        body.events = [AppleEvent(**e) for e in over["events"]]
    with pytest.raises(ValueError):
        await apple.snapshot(USER, body)
    assert not db.calls


def test_feed_reports_staleness_partial_coverage_and_inclusive_all_day_dates():
    begin, finish = datetime(2026, 10, 6, tzinfo=timezone.utc), datetime(2026, 10, 7, tzinfo=timezone.utc)
    assert apple.events_in(None, begin, finish)["status"] == "not_connected"
    assert apple.events_in(row(synced_at=None), begin, finish)["events"] == []
    assert apple.events_in(row(), begin, finish, "FOCUS")["events"] == [EVENT]
    assert apple.events_in(row(), begin, finish, "other")["events"] == []
    assert apple.events_in(row(complete=False), begin, finish)["status"] == "partial"
    assert apple.events_in(row(synced_at=NOW-timedelta(minutes=6)), begin, finish)["status"] == "stale"
    assert apple.events_in(row(window_start=finish), begin, finish)["status"] == "out_of_range"
    timed = {**EVENT, "all_day": False, "start": "2026-10-06T12:00:00Z", "end": "2026-10-06T13:00:00Z"}
    assert apple.events_in(row(snapshot=[timed]), begin, finish)["events"] == [timed]


@pytest.mark.asyncio
async def test_connection_compatibility_and_feed(db):
    assert (await apple.connection(USER))["user_id"] == USER
    db.on("SELECT *", None)
    assert await apple.connection(USER) is None
    db.on("SELECT *", asyncpg.UndefinedTableError())
    assert await apple.connection(USER) is None
    db.on("SELECT *", row())
    assert (await apple.feed(USER, datetime(2026, 10, 6, tzinfo=timezone.utc), datetime(2026, 10, 7, tzinfo=timezone.utc)))["events"] == [EVENT]


@pytest.mark.asyncio
async def test_enqueue_locks_connection_and_binds_action_to_owner_and_generation(db):
    action = uuid4()
    db.on("INSERT INTO mw_apple_calendar_actions", action)
    for operation in ("create", "update", "delete"):
        assert await apple.enqueue(USER, str(CONN), operation, {"event": EVENT}) == str(action)
    assert all(c[2][:2] == (USER, CONN) for c in db.ran("INSERT INTO mw_apple_calendar_actions"))
    assert "FOR UPDATE" in db.ran("SELECT *")[0][1]
    db.on("SELECT count(*)", 30)
    with pytest.raises(ValueError, match="pending"):
        await apple.enqueue(USER, str(CONN), "create", {})


@pytest.mark.asyncio
@pytest.mark.parametrize("connection_row,connection_id,payload,operation", [
    (None, CONN, {"event": EVENT}, "update"),
    (row(), uuid4(), {"event": EVENT}, "update"),
    (row(synced_at=None), CONN, {"event": EVENT}, "update"),
    (row(synced_at=NOW-timedelta(minutes=6)), CONN, {"event": EVENT}, "update"),
    (row(), CONN, {"event": {**EVENT, "modified": "old"}}, "update"),
    (row(snapshot=[{**EVENT, "editable": False}]), CONN, {"event": {**EVENT, "editable": False}}, "delete"),
    (row(snapshot=[]), CONN, {"event": EVENT}, "delete"),
    (row(), CONN, {}, "invalid"),
])
async def test_enqueue_refuses_stale_reconnected_readonly_and_changed_events(db, connection_row, connection_id, payload, operation):
    db.on("SELECT *", connection_row)
    with pytest.raises(ValueError):
        await apple.enqueue(USER, str(connection_id), operation, payload)
    assert not db.ran("INSERT INTO mw_apple_calendar_actions")


@pytest.mark.asyncio
async def test_claim_rechecks_consent_and_never_requeues_uncertain_writes(db, monkeypatch):
    active = AsyncMock(return_value={"calendar": {}})
    monkeypatch.setattr(apple.grants, "load_grants", active)
    action = uuid4()
    db.on("RETURNING id, operation, payload", [{"id": action, "operation": "create", "payload": {"fields": {"title": "Focus"}}}])
    actions = await apple.claim(USER, CONN)
    assert actions[0]["id"] == str(action)
    query = db.ran("RETURNING id, operation, payload")[0][1]
    assert "SKIP LOCKED" in query and "status = 'pending'" in query
    assert db.ran("status = 'unknown'") and db.ran("status = 'failed'")
    active.return_value = {}
    assert await apple.claim(USER, CONN) == []
    assert db.ran("status = 'cancelled'")


@pytest.mark.asyncio
async def test_acknowledgment_is_idempotent_and_history_is_private(db):
    action = uuid4()
    await apple.acknowledge(USER, CONN, action, AppleActionResult(status="done"))
    query, args = db.ran("SET status = $4")[0][1:]
    assert "status = 'claimed'" in query and args[:3] == (action, USER, CONN)
    db.on("SELECT id, operation, status, error", [{"id": action, "operation": "create", "status": "done", "error": None}])
    assert (await apple.recent(USER))[0]["id"] == str(action)
    assert db.ran("SELECT id, operation, status, error")[0][2] == (USER,)


@pytest.mark.asyncio
async def test_routes_bind_every_operation_to_current_user(monkeypatch):
    user = SimpleNamespace(id=USER)
    fake = SimpleNamespace(**{name: AsyncMock() for name in ("connect", "disconnect", "snapshot", "acknowledge")},
        connection=AsyncMock(return_value=row()), claim=AsyncMock(return_value=[]), recent=AsyncMock(return_value=[]))
    for name, method in vars(fake).items():
        monkeypatch.setattr(apple, name, method)
    assert (await routes.apple_connection(user))["connected"]
    await routes.connect_apple(config(), user)
    await routes.disconnect_apple(CONN, user)
    await routes.sync_apple(snapshot(), user)
    assert await routes.claim_apple(CONN, user) == {"actions": []}
    await routes.acknowledge_apple(CONN, uuid4(), AppleActionResult(status="done"), user)
    for method in vars(fake).values():
        assert method.await_args.args[0] == USER
    with pytest.raises(HTTPException) as caught:
        await routes.connect_apple(config().model_copy(update={"user_id": uuid4()}), user)
    assert caught.value.status_code == 409
    for name, invocation in [
        ("connect", lambda: routes.connect_apple(config(), user)),
        ("snapshot", lambda: routes.sync_apple(snapshot(), user)),
        ("claim", lambda: routes.claim_apple(CONN, user)),
    ]:
        getattr(fake, name).side_effect = ValueError("not allowed")
        with pytest.raises(HTTPException):
            await invocation()
    fake.connection.return_value = None
    assert not (await routes.apple_connection(user))["connected"]
