"""Break-reminder delivery record: writes, filters, tenant scope, auth (no DB)."""

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user
from app.matcha.routes.employee_schedule import break_reminder_events as route
from app.matcha.services.scheduling import break_reminder_events as events


class _RecordConn:
    def __init__(self, returned=True):
        self.returned = returned
        self.calls = []

    async def fetchval(self, query, *params):
        self.calls.append((query, params))
        return uuid4() if self.returned else None


def _params(conn) -> dict:
    query, params = conn.calls[-1]
    columns = query.split("(", 1)[1].split(")", 1)[0]
    names = [name.strip() for name in columns.replace("\n", " ").split(",")]
    return dict(zip(names, params))


@pytest.mark.asyncio
async def test_record_event_writes_every_audit_field_once():
    conn = _RecordConn()
    company, employee, location = uuid4(), uuid4(), uuid4()

    written = await events.record_event(
        conn, company_id=company, channel="email", reminder_type="daily_digest",
        recipient_type="employee", outcome="failed", event_date=date(2026, 9, 23),
        outcome_detail="x" * 900, recipient="Ana@Example.com", employee_id=employee,
        employee_name="Ana Ruiz", location_id=location, location_name="Downtown",
        location_timezone="America/Los_Angeles", context={"digest_date": "2026-09-23"},
    )

    assert written is True
    query, _ = conn.calls[-1]
    assert "INSERT INTO schedule_break_reminder_events" in query
    # Append-only: a repeat is dropped, never merged into the existing row.
    assert "DO NOTHING" in query and "DO UPDATE" not in query
    row = _params(conn)
    assert row["company_id"] == company
    assert row["recipient"] == "ana@example.com"
    assert row["covered_employee_ids"] == [employee]  # an employee event covers that employee
    assert row["location_timezone"] == "America/Los_Angeles"
    assert len(row["outcome_detail"]) == 500
    assert row["outcome"] == "failed"


@pytest.mark.asyncio
async def test_record_event_rejects_unknown_outcome_and_bad_timezone_is_stored_as_utc():
    with pytest.raises(ValueError, match="Unknown break reminder outcome"):
        await events.record_event(
            _RecordConn(), company_id=uuid4(), channel="push", reminder_type="break_start",
            recipient_type="employee", outcome="read", event_date=date(2026, 9, 23),
        )
    conn = _RecordConn()
    await events.record_event(
        conn, company_id=uuid4(), channel="push", reminder_type="break_start",
        recipient_type="employee", outcome="accepted", event_date=date(2026, 9, 23),
        location_timezone="Not/AZone",
    )
    assert _params(conn)["location_timezone"] == "UTC"


@pytest.mark.asyncio
async def test_duplicate_dedupe_key_reports_not_written():
    written = await events.record_event(
        _RecordConn(returned=False), company_id=uuid4(), channel="push",
        reminder_type="break_start", recipient_type="employee", outcome="accepted",
        event_date=date(2026, 9, 23), dedupe_key="break_start:x",
    )
    assert written is False


# ── Filters ──────────────────────────────────────────────────────────────────


def test_filters_always_scope_to_the_tenant_first():
    company = uuid4()
    where, params = events.event_filters(company, start=None, end=None, location_id=None, employee_id=None)
    assert where == "ev.company_id = $1"
    assert params == [company]


@pytest.mark.parametrize("start,end,location,employee", [
    (date(2026, 9, 1), None, None, None),
    (None, date(2026, 9, 30), None, None),
    (None, None, "loc", None),
    (None, None, None, "emp"),
    (date(2026, 9, 1), date(2026, 9, 1), "loc", "emp"),
    (date(2026, 9, 1), date(2026, 9, 30), None, "emp"),
])
def test_filters_combine_in_any_combination(start, end, location, employee):
    company, location_id, employee_id = uuid4(), uuid4(), uuid4()
    where, params = events.event_filters(
        company, start=start, end=end,
        location_id=location_id if location else None,
        employee_id=employee_id if employee else None,
    )
    assert where.startswith("ev.company_id = $1")
    assert params[0] == company
    # Both date ends are inclusive days.
    assert ("ev.event_date >= $" in where) is (start is not None)
    assert ("ev.event_date <= $" in where) is (end is not None)
    assert ("ev.location_id = $" in where) is bool(location)
    if employee:
        position = params.index(employee_id) + 1
        # A manager digest listing the employee is part of their history.
        assert f"(ev.employee_id = ${position} OR ${position} = ANY(ev.covered_employee_ids))" in where
    assert where.count("$") == len(params) + (1 if employee else 0)


class _ListConn:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    async def fetchval(self, query, *params):
        self.queries.append((query, params))
        return len(self.rows)

    async def fetch(self, query, *params):
        self.queries.append((query, params))
        return self.rows


def _event_row(**overrides):
    row = {
        "id": uuid4(), "occurred_at": datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc),
        "event_date": date(2026, 9, 23), "channel": "push", "reminder_type": "break_start",
        "recipient_type": "employee", "recipient": None, "employee_id": uuid4(),
        "employee_name": "Ana Ruiz", "covered_employee_ids": [], "location_id": uuid4(),
        "location_name": "Downtown", "location_timezone": "America/Los_Angeles",
        "shift_id": uuid4(), "break_kind": "meal",
        "break_start_local": datetime(2026, 9, 23, 12, 0), "break_duration_minutes": 30,
        "context": '{"ordinal": 1}', "outcome": "accepted", "outcome_detail": "ok",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_events_pages_newest_first_and_serializes():
    conn = _ListConn([_event_row(), _event_row(break_kind=None, channel="email", context={"breaks": []})])
    company = uuid4()

    rows, total = await events.list_events(conn, company, start=date(2026, 9, 23), limit=50, offset=100)

    assert total == 2
    list_query, list_params = conn.queries[-1]
    assert "ORDER BY ev.occurred_at DESC, ev.id DESC" in list_query
    assert list_params[0] == company and list_params[-2:] == (50, 100)
    assert rows[0]["break"] == {"kind": "meal", "start_local": "2026-09-23T12:00:00", "duration_minutes": 30}
    assert rows[0]["context"] == {"ordinal": 1}
    assert rows[1]["break"] is None and rows[1]["context"] == {"breaks": []}


@pytest.mark.asyncio
async def test_filter_options_come_from_the_history_not_the_live_roster():
    class _Conn:
        def __init__(self):
            self.queries = []

        async def fetch(self, query, *params):
            self.queries.append((query, params))
            if "location_id" in query.split("FROM")[0]:
                return [{"location_id": uuid4(), "location_name": "Mission"}]
            return [{"employee_id": uuid4(), "employee_name": "zed"}, {"employee_id": uuid4(), "employee_name": "Ana"}]

    conn = _Conn()
    company = uuid4()
    options = await events.filter_options(conn, company)

    assert [item["name"] for item in options["employees"]] == ["Ana", "zed"]
    assert options["locations"][0]["name"] == "Mission"
    assert all("FROM schedule_break_reminder_events" in q and "employees e" not in q for q, _ in conn.queries)
    assert all(params == (company,) for _, params in conn.queries)


# ── Route: auth, tenant scope, validation ────────────────────────────────────


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


def _client(monkeypatch, *, role, company_id=None):
    captured = {}

    async def company(current_user):
        if company_id is None:
            raise HTTPException(status_code=403, detail="No company associated with this account")
        return company_id

    async def fake_list(conn, company_arg, **kwargs):
        captured["company"] = company_arg
        captured["filters"] = kwargs
        return [], 0

    monkeypatch.setattr(route, "require_company_id", company)
    monkeypatch.setattr(route, "get_connection", lambda: _Ctx(object()))
    monkeypatch.setattr(route, "list_events", fake_list)
    app = FastAPI()
    app.include_router(route.router, prefix="/employee-schedule")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), role=role)
    return TestClient(app), captured


@pytest.mark.parametrize("role", ["employee", "candidate", "broker", "creator"])
def test_employees_and_other_roles_cannot_read_delivery_history(monkeypatch, role):
    client, captured = _client(monkeypatch, role=role, company_id=uuid4())
    response = client.get("/employee-schedule/break-reminder-events")
    assert response.status_code == 403
    assert captured == {}


def test_caller_without_a_company_is_refused(monkeypatch):
    client, captured = _client(monkeypatch, role="individual", company_id=None)
    assert client.get("/employee-schedule/break-reminder-events").status_code == 403
    assert captured == {}


def test_company_comes_from_the_caller_never_the_query(monkeypatch):
    own = uuid4()
    client, captured = _client(monkeypatch, role="client", company_id=own)
    response = client.get(
        "/employee-schedule/break-reminder-events",
        params={"company_id": str(uuid4()), "start": "2026-09-01", "end": "2026-09-01"},
    )
    assert response.status_code == 200
    assert response.json() == {"events": [], "total": 0}
    assert captured["company"] == own
    # start == end is one whole inclusive day, not an empty range.
    assert captured["filters"]["start"] == captured["filters"]["end"] == date(2026, 9, 1)


def test_inverted_range_is_a_422(monkeypatch):
    client, captured = _client(monkeypatch, role="client", company_id=uuid4())
    response = client.get(
        "/employee-schedule/break-reminder-events", params={"start": "2026-09-02", "end": "2026-09-01"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "End date must be on or after the start date"
    assert captured == {}


def test_malformed_filters_are_rejected_before_any_query(monkeypatch):
    client, captured = _client(monkeypatch, role="client", company_id=uuid4())
    assert client.get("/employee-schedule/break-reminder-events", params={"employee_id": "nope"}).status_code == 422
    assert client.get("/employee-schedule/break-reminder-events", params={"start": "09/01/2026"}).status_code == 422
    assert client.get("/employee-schedule/break-reminder-events", params={"limit": 0}).status_code == 422
    assert captured == {}


def test_routes_live_under_the_employee_schedule_gate():
    from app.matcha.routes import employee_schedule
    from tests._helpers.routes import iter_api_routes

    paths = {route.path for route in iter_api_routes(employee_schedule.router)}
    assert {"/break-reminder-events", "/break-reminder-events/filter-options"} <= paths
    mount = (Path(__file__).parents[2] / "app/matcha/routes/__init__.py").read_text()
    assert 'include_router(employee_schedule_router, prefix="/employee-schedule",' in mount
    assert 'require_feature("employee_schedule")' in mount.split("include_router(employee_schedule_router", 1)[1][:200]


# ── Migration invariants ─────────────────────────────────────────────────────


def test_migration_keeps_the_record_append_only_and_self_contained():
    source = (Path(__file__).parents[2] / "alembic/versions/empsched28_break_reminder_events.py").read_text()
    assert 'down_revision = "empsched27"' in source
    assert "BEFORE UPDATE ON schedule_break_reminder_events" in source
    assert "RAISE EXCEPTION" in source
    # History must outlive roster rows; an FK SET NULL would itself be an UPDATE.
    table = source.split("CREATE TABLE schedule_break_reminder_events", 1)[1].split('""")', 1)[0]
    assert table.count("REFERENCES") == 1 and "REFERENCES companies(id) ON DELETE CASCADE" in table
    assert "CHECK (outcome IN ('accepted', 'failed', 'unavailable'))" in table
    # Pushing to every phone is opt-in.
    assert "'schedule_break_reminders'" in source and "false, 500)" in source
