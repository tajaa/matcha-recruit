"""Employee availability changes are manager-reviewed, not immediate writes.

Covers the five behaviours the flow is defined by: a submission stays pending
and writes nothing, a start date inside a published week is refused, approval
applies the change (now if it is due, later if it is not), rejection leaves the
availability alone, and the direct employee write path is gone.
"""

from contextlib import asynccontextmanager
from datetime import date, time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.matcha.models.scheduling.employee_schedule import (
    AvailabilityChangeRequestCreate, AvailabilityReplace, AvailabilityWindow,
    RequestReview, ScheduleRequestCreate,
)
from app.matcha.routes.employee_portal import schedule as portal_schedule
from app.matcha.routes.employee_schedule import requests as review_routes
from app.matcha.services.scheduling import availability_requests
from app.matcha.services.scheduling.availability_requests import (
    parse_proposed_availability, promote_due_availability_changes,
    serialize_proposed_availability, summarize_proposed_availability,
)
from app.matcha.services.scheduling.time_off_guard import (
    PUBLISHED_WEEK_AVAILABILITY_DETAIL,
)


TODAY = date(2026, 9, 8)
NEXT_MONTH = date(2026, 10, 5)


def _payload(effective_on=NEXT_MONTH, reason="New class schedule"):
    return AvailabilityChangeRequestCreate(
        availability=AvailabilityReplace(
            availability_state="windows",
            windows=[AvailabilityWindow(
                weekday=1, start_time=time(9, 0), end_time=time(17, 0),
            )],
        ),
        effective_on=effective_on,
        reason=reason,
    )


class FakePortalConn:
    """Answers the four probes the submit endpoint makes, recording writes."""

    def __init__(self, *, published_week=False, open_request=False, today=TODAY):
        self.published_week = published_week
        self.open_request = open_request
        self.today = today
        self.executed: list[tuple] = []
        self.inserted: dict | None = None

    async def fetchval(self, query, *args):
        q = " ".join(query.split())
        if "CURRENT_DATE" in q and "schedule_requests" not in q:
            return self.today
        if "EXTRACT(DOW FROM s.starts_at)" in q:
            return self.published_week
        if "request_type = 'availability'" in q and "FOR UPDATE" in q:
            return 1 if self.open_request else None
        if q.startswith("INSERT INTO schedule_requests"):
            self.inserted = {"query": q, "args": args}
            return uuid4()
        raise AssertionError(f"unexpected fetchval: {q[:90]}")

    async def fetchrow(self, query, *args):
        return {
            "id": uuid4(), "employee_id": uuid4(), "request_type": "availability",
            "shift_id": None, "target_employee_id": None, "counter_shift_id": None,
            "counterparty_confirmed_at": None, "unavailable_start": None,
            "unavailable_end": None, "reason": "New class schedule",
            "status": "awaiting_manager", "review_notes": None, "reviewed_at": None,
            "created_at": None, "first_name": "Dana", "last_name": "Whitfield",
            "proposed_availability": serialize_proposed_availability(
                "windows", [AvailabilityWindow(
                    weekday=1, start_time=time(9, 0), end_time=time(17, 0))],
            ),
            "availability_effective_on": NEXT_MONTH,
            "availability_applied_at": None,
        }

    async def execute(self, query, *args):
        self.executed.append((" ".join(query.split()), args))
        return "INSERT 0 1"

    def transaction(self):
        conn = self

        @asynccontextmanager
        async def _txn():
            yield conn
        return _txn()

    def is_in_transaction(self):
        return False


def _employee():
    return {"id": uuid4(), "org_id": uuid4(), "user_id": uuid4()}


def _patch_connection(monkeypatch, module, conn):
    @asynccontextmanager
    async def fake_get_connection():
        yield conn

    monkeypatch.setattr(module, "get_connection", fake_get_connection)


# ── Submission ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submission_is_pending_and_writes_no_availability(monkeypatch):
    conn = FakePortalConn()
    _patch_connection(monkeypatch, portal_schedule, conn)

    result = await portal_schedule.request_my_availability_change(_payload(), _employee())

    assert result["status"] == "awaiting_manager"
    assert result["request_type"] == "availability"
    assert result["availability_effective_on"] == str(NEXT_MONTH)
    assert conn.inserted is not None
    assert "'availability'" in conn.inserted["query"]
    # Nothing touched the live availability table.
    assert not any("schedule_employee_availability" in q for q, _ in conn.executed)


@pytest.mark.asyncio
async def test_start_date_inside_a_published_week_is_refused(monkeypatch):
    conn = FakePortalConn(published_week=True)
    _patch_connection(monkeypatch, portal_schedule, conn)

    with pytest.raises(HTTPException) as exc_info:
        await portal_schedule.request_my_availability_change(_payload(), _employee())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == PUBLISHED_WEEK_AVAILABILITY_DETAIL
    assert conn.inserted is None


@pytest.mark.asyncio
async def test_a_start_date_in_the_past_is_refused(monkeypatch):
    conn = FakePortalConn()
    _patch_connection(monkeypatch, portal_schedule, conn)

    with pytest.raises(HTTPException) as exc_info:
        await portal_schedule.request_my_availability_change(
            _payload(effective_on=date(2026, 9, 1)), _employee(),
        )

    assert exc_info.value.status_code == 422
    assert conn.inserted is None


@pytest.mark.asyncio
async def test_only_one_availability_request_may_await_review(monkeypatch):
    conn = FakePortalConn(open_request=True)
    _patch_connection(monkeypatch, portal_schedule, conn)

    with pytest.raises(HTTPException) as exc_info:
        await portal_schedule.request_my_availability_change(_payload(), _employee())

    assert exc_info.value.status_code == 409
    assert "awaiting review" in exc_info.value.detail
    assert conn.inserted is None


def test_the_generic_request_endpoint_will_not_take_an_availability_change():
    with pytest.raises(ValidationError, match="availability-requests"):
        ScheduleRequestCreate(request_type="availability")


def test_the_immediate_employee_write_path_is_gone():
    portal = Path(__file__).parents[2] / "app/matcha/routes/employee_portal/schedule.py"
    source = portal.read_text()
    assert '@router.put("/me/schedule/availability"' not in source
    assert "replace_availability_core(" not in source
    assert '@router.post("/me/schedule/availability-requests"' in source


# ── Proposal round trip ────────────────────────────────────────────────────

def test_proposed_availability_round_trips_through_jsonb():
    windows = [
        AvailabilityWindow(weekday=1, start_time=time(9, 0), end_time=time(17, 0)),
        AvailabilityWindow(weekday=3, start_time=time(12, 0), end_time=time(20, 30)),
    ]
    doc = serialize_proposed_availability("windows", windows)

    state, parsed = parse_proposed_availability(doc)
    assert state == "windows"
    assert [(w.weekday, w.start_time, w.end_time) for w in parsed] == [
        (1, time(9, 0), time(17, 0)), (3, time(12, 0), time(20, 30)),
    ]
    assert summarize_proposed_availability(doc) == {
        "availability_state": "windows",
        "windows": [
            {"weekday": 1, "start_time": "09:00", "end_time": "17:00"},
            {"weekday": 3, "start_time": "12:00", "end_time": "20:30"},
        ],
    }


def test_an_empty_proposal_is_stored_as_an_explicit_always_available_state():
    """The legacy "empty list means always available" inference is resolved at
    submit time, so approval days later never has to re-guess it."""
    state, parsed = parse_proposed_availability(
        serialize_proposed_availability("always_available", []),
    )
    assert state == "always_available"
    assert parsed == []


# ── Manager review ─────────────────────────────────────────────────────────

class FakeReviewConn:
    def __init__(self, *, effective_on, today=TODAY):
        self.request_id = uuid4()
        self.company_id = uuid4()
        self.employee_id = uuid4()
        self.effective_on = effective_on
        self.today = today
        self.executed: list[tuple] = []
        self.audits: list[dict] = []

    def _request_row(self):
        return {
            "id": self.request_id, "company_id": self.company_id,
            "request_type": "availability", "shift_id": None,
            "employee_id": self.employee_id, "target_employee_id": None,
            "counter_shift_id": None, "counterparty_confirmed_at": None,
            "status": "awaiting_manager",
            "proposed_availability": serialize_proposed_availability(
                "windows", [AvailabilityWindow(
                    weekday=2, start_time=time(10, 0), end_time=time(18, 0))],
            ),
            "availability_effective_on": self.effective_on,
        }

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if "FROM schedule_requests WHERE id" in q:
            return self._request_row()
        if "INSERT INTO employee_schedule_profiles" in q:
            return {"availability_state": "windows", "availability_confirmed_at": None,
                    "availability_confirmed_by": None, "min_weekly_minutes": None,
                    "target_weekly_minutes": None, "max_weekly_minutes": None,
                    "max_consecutive_days": None, "allow_overtime": False,
                    "prefer_extra_hours": False}
        if "FROM employee_schedule_profiles" in q:
            return None
        # The final serialize_request read.
        row = self._request_row()
        row.update({
            "unavailable_start": None, "unavailable_end": None, "reason": None,
            "status": "approved", "review_notes": None, "reviewed_at": None,
            "created_at": None, "first_name": "Dana", "last_name": "Whitfield",
            "availability_applied_at": None,
        })
        return row

    async def fetchval(self, query, *args):
        q = " ".join(query.split())
        if "CURRENT_DATE" in q:
            return self.today
        return None

    async def execute(self, query, *args):
        self.executed.append((" ".join(query.split()), args))
        return "UPDATE 1"

    async def fetch(self, query, *args):
        return []

    def transaction(self):
        conn = self

        @asynccontextmanager
        async def _txn():
            yield conn
        return _txn()

    def is_in_transaction(self):
        return True


class _User:
    id = uuid4()


def _patch_review(monkeypatch, conn):
    _patch_connection(monkeypatch, review_routes, conn)
    monkeypatch.setattr(
        review_routes, "require_company_id",
        lambda current_user: _async_value(conn.company_id),
    )
    monkeypatch.setattr(
        review_routes, "mark_manager_ready_notifications_resolved",
        lambda *a, **k: _async_value(0),
    )


def _async_value(value):
    async def _coro():
        return value
    return _coro()


@pytest.mark.asyncio
async def test_approving_a_due_change_applies_it(monkeypatch):
    conn = FakeReviewConn(effective_on=TODAY)
    _patch_review(monkeypatch, conn)

    await review_routes.review_request(
        conn.request_id, RequestReview(decision="approved"), _User(),
    )

    statements = [q for q, _ in conn.executed]
    assert any("DELETE FROM schedule_employee_availability" in q for q in statements)
    assert any("INSERT INTO schedule_employee_availability" in q for q in statements)
    assert any("availability_applied_at = NOW()" in q for q in statements)


@pytest.mark.asyncio
async def test_approving_a_future_dated_change_defers_the_write(monkeypatch):
    conn = FakeReviewConn(effective_on=NEXT_MONTH)
    _patch_review(monkeypatch, conn)

    await review_routes.review_request(
        conn.request_id, RequestReview(decision="approved"), _User(),
    )

    statements = [q for q, _ in conn.executed]
    assert not any("schedule_employee_availability" in q for q in statements)
    assert not any("availability_applied_at = NOW()" in q for q in statements)
    assert any("SET status = $3" in q for q in statements)


@pytest.mark.asyncio
async def test_rejecting_leaves_the_current_availability_untouched(monkeypatch):
    conn = FakeReviewConn(effective_on=TODAY)
    _patch_review(monkeypatch, conn)

    await review_routes.review_request(
        conn.request_id, RequestReview(decision="denied"), _User(),
    )

    statements = [q for q, _ in conn.executed]
    assert not any("schedule_employee_availability" in q for q in statements)
    assert not any("availability_applied_at" in q for q in statements)


# ── Promotion ──────────────────────────────────────────────────────────────

class FakePromotionConn:
    """One due request the first time round, none after it is applied."""

    def __init__(self, due_rows):
        self.due_rows = due_rows
        self.applied: list = []
        self.executed: list[str] = []

    async def fetch(self, query, *args):
        rows, self.due_rows = self.due_rows, []
        return rows

    async def execute(self, query, *args):
        self.executed.append(" ".join(query.split()))
        return "UPDATE 1"

    async def fetchrow(self, query, *args):
        return None

    def is_in_transaction(self):
        return True


@pytest.mark.asyncio
async def test_promotion_applies_a_due_change_then_finds_nothing_left(monkeypatch):
    company_id, employee_id = uuid4(), uuid4()
    row = {
        "id": uuid4(), "company_id": company_id, "employee_id": employee_id,
        "proposed_availability": serialize_proposed_availability("always_available", []),
        "availability_effective_on": TODAY, "reviewed_by": uuid4(),
    }
    conn = FakePromotionConn([row])
    applied: list = []

    async def fake_apply(_conn, request_row, *, actor_user_id):
        applied.append((request_row["id"], actor_user_id))
        return {}

    monkeypatch.setattr(availability_requests, "apply_availability_request", fake_apply)

    assert await promote_due_availability_changes(conn, company_id, [employee_id]) == 1
    assert applied == [(row["id"], row["reviewed_by"])]
    assert await promote_due_availability_changes(conn, company_id, [employee_id]) == 0


@pytest.mark.asyncio
async def test_promotion_orders_by_effective_date_so_the_latest_change_wins():
    seen: dict = {}

    class Conn(FakePromotionConn):
        async def fetch(self, query, *args):
            seen["query"] = " ".join(query.split())
            return []

    await promote_due_availability_changes(Conn([]), uuid4(), [uuid4()])
    assert "ORDER BY availability_effective_on, created_at" in seen["query"]
    assert "status = 'approved'" in seen["query"]
    assert "availability_applied_at IS NULL" in seen["query"]
    assert "availability_effective_on <= CURRENT_DATE" in seen["query"]
    assert "FOR UPDATE SKIP LOCKED" in seen["query"]


def test_every_availability_read_promotes_first():
    """Promotion is read-driven: these two functions are the only ways stored
    availability is ever observed, so neither may skip it."""
    services = Path(__file__).parents[2] / "app/matcha/services/scheduling"
    for name in ("shift_writes.py", "schedule_profiles.py"):
        source = (services / name).read_text()
        assert "promote_due_availability_changes(" in source, name
