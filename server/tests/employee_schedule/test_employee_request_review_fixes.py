"""Regression tests for the 2026-09-27 Matcha Schedule review (no database).

Each test names the defect it pins: requests reaching the manager queue in a
state approval can only refuse, missing re-notification, a terminated employee
keeping portal access, and the fetch_shifts parameter shadowing that hid an
employee's own manager note whenever any forced assignment existed.
"""

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

from app.matcha import dependencies as deps
from app.matcha.models.scheduling.employee_schedule import (
    AvailabilityChangeRequestCreate, CounterpartyAccept, RequestReview, ScheduleRequestCreate,
)
from app.matcha.routes.employee_portal import schedule as portal
from app.matcha.routes.employee_schedule import _shared as shared
from app.matcha.routes.employee_schedule import requests as manager
from app.matcha.services.scheduling import schedule_request_notifications as manager_notices
from app.matcha.services.scheduling import time_off_guard

NOW = datetime.now(timezone.utc)
FUTURE = NOW + timedelta(days=1)
PAST = NOW - timedelta(hours=2)


def _connection(conn):
    @asynccontextmanager
    async def connection():
        yield conn
    return connection


class _Tx:
    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


# ── fetch_shifts: the caller's own fields survive an override row ─────────────

class _ShiftsConn:
    def __init__(self, shift_id, me, coworker):
        self.shift_id, self.me, self.coworker = shift_id, me, coworker

    async def fetch(self, query, *_args):
        if "FROM schedule_shifts s" in query:
            return [{
                "id": self.shift_id, "company_id": uuid4(), "location_id": None,
                "template_id": None, "series_id": None, "role": "Barista",
                "department": None, "starts_at": FUTURE, "ends_at": FUTURE + timedelta(hours=8),
                "break_minutes": 30, "required_staff": 2, "color": None, "notes": None,
                "status": "published", "kind": "regular", "training_requirement_id": None,
                "job_id": None, "published_at": NOW, "created_at": NOW, "updated_at": NOW,
            }]
        if "FROM schedule_shift_assignments a" in query:
            return [
                {"shift_id": self.shift_id, "employee_id": person, "status": "assigned",
                 "manager_note": note, "manager_note_visible_to_employee": True,
                 "manager_note_include_in_location_digest": False,
                 "manager_note_send_employee_notice": True,
                 "compliance_guidance": '{"meal": "by 11:30"}',
                 "planned_breaks": '[{"kind": "meal", "ordinal": 1}]',
                 "first_name": name, "last_name": "X", "job_title": "Barista"}
                for person, note, name in (
                    (self.me, "Bring your apron", "Me"),
                    (self.coworker, "Private to coworker", "Co"),
                )
            ]
        if "assignment.availability_override" in query:
            # The coworker was forced outside availability on this shift.
            return [{"entity_id": self.shift_id, "created_at": NOW,
                     "details": {"employee_id": str(self.coworker), "violations": []}}]
        raise AssertionError(query)


@pytest.mark.asyncio
async def test_portal_caller_keeps_own_note_when_a_coworker_was_forced():
    shift_id, me, coworker = uuid4(), uuid4(), uuid4()
    shifts = await shared.fetch_shifts(
        _ShiftsConn(shift_id, me, coworker), uuid4(), NOW, NOW + timedelta(days=7),
        status="published", employee_id=me,
    )
    mine, theirs = shifts[0]["assignments"]
    assert mine["manager_note"] == "Bring your apron"
    assert mine["compliance_guidance"] == {"meal": "by 11:30"}
    assert mine["planned_breaks"] == [{"kind": "meal", "ordinal": 1}]
    assert mine["availability_overridden"] is False
    # Nothing private about the coworker, including that they were forced.
    assert "manager_note" not in theirs
    assert "availability_overridden" not in theirs
    assert "availability_override_at" not in theirs


@pytest.mark.asyncio
async def test_admin_view_keeps_note_controls_when_an_override_exists():
    shift_id, me, coworker = uuid4(), uuid4(), uuid4()
    shifts = await shared.fetch_shifts(
        _ShiftsConn(shift_id, me, coworker), uuid4(), NOW, NOW + timedelta(days=7),
    )
    mine, theirs = shifts[0]["assignments"]
    for assignment in (mine, theirs):
        assert assignment["manager_note_send_employee_notice"] is True
        assert "planned_breaks" in assignment
    assert theirs["availability_overridden"] is True
    assert theirs["availability_override_at"]


# ── Approvability gates shared by claim / accept / approval ───────────────────

_SHIFT = {"id": uuid4(), "location_id": uuid4(), "starts_at": FUTURE,
          "ends_at": FUTURE + timedelta(hours=8), "break_minutes": 0, "job_id": None,
          "status": "published", "kind": "regular", "training_requirement_id": None}


@pytest.mark.asyncio
async def test_compliance_block_is_refused_but_advisories_pass(monkeypatch):
    async def block(*_args, **_kwargs):
        return [{"severity": "block", "check": "credential", "message": "Food Handler Card expired"}]

    async def advisory(*_args, **_kwargs):
        return [{"severity": "advisory", "check": "rest_gap", "message": "Short rest"}]

    monkeypatch.setattr(manager, "compliance_violations_for", block)
    with pytest.raises(HTTPException) as exc:
        await manager.assert_no_compliance_block(object(), uuid4(), _SHIFT, uuid4())
    assert exc.value.status_code == 422

    monkeypatch.setattr(manager, "compliance_violations_for", advisory)
    await manager.assert_no_compliance_block(object(), uuid4(), _SHIFT, uuid4())


@pytest.mark.asyncio
async def test_assert_approvable_runs_active_store_then_compliance(monkeypatch):
    calls = []

    async def active(_conn, _company, employee_id):
        calls.append(("active", employee_id))

    async def store(_conn, _company, employee_id, location_id):
        calls.append(("store", location_id))

    async def compliance(_conn, _company, _shift, _employee, *, exclude_shift_id):
        calls.append(("compliance", exclude_shift_id))

    employee_id, exclude = uuid4(), uuid4()
    monkeypatch.setattr(manager, "_active_employee", active)
    monkeypatch.setattr(manager, "assert_employee_schedulable_at", store)
    monkeypatch.setattr(manager, "assert_no_compliance_block", compliance)
    await manager.assert_approvable(object(), uuid4(), _SHIFT, employee_id, exclude_shift_id=exclude)
    assert calls == [("active", employee_id), ("store", _SHIFT["location_id"]), ("compliance", exclude)]


@pytest.mark.asyncio
async def test_compliance_violations_use_the_required_meal_break(monkeypatch):
    seen = {}

    async def plan(*_args, **_kwargs):
        return "plan"

    async def check(_conn, _company, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(manager, "resolve_shift_break_plan", plan)
    monkeypatch.setattr(manager, "minimum_meal_break_minutes", lambda _plan: 30)
    monkeypatch.setattr(manager, "check_shift_compliance", check)
    assert await manager.compliance_violations_for(
        object(), uuid4(), _SHIFT, uuid4(), exclude_shift_id=None,
    ) == []
    assert seen["break_minutes"] == 30 and seen["fw_event"] == "assign"


def test_started_gate_uses_the_store_clock():
    manager.assert_not_started({"starts_at": FUTURE, "timezone": None})
    with pytest.raises(HTTPException) as exc:
        manager.assert_not_started({"starts_at": PAST, "timezone": "UTC"}, detail="gone")
    assert exc.value.status_code == 409 and exc.value.detail == "gone"


# ── Accept: store / compliance / started, for both people who gain a shift ────

def _accept_env(monkeypatch, *, request_type, starts_at, approvable_error=None):
    company_id, owner_id, accepter_id, shift_id, counter_id, request_id = (uuid4() for _ in range(6))
    checked = []

    class Conn(_Tx):
        async def fetchrow(self, query, *_args):
            if "FOR UPDATE" in query:
                return {"id": request_id, "employee_id": owner_id, "request_type": request_type,
                        "shift_id": shift_id,
                        "target_employee_id": accepter_id if request_type == "swap" else None,
                        "counter_shift_id": counter_id if request_type == "swap" else None,
                        "status": "awaiting_counterparty"}
            return {"status": "awaiting_manager"}

        async def fetchval(self, query, *_args):
            if "RETURNING" in query:
                return NOW
            return "active" if "employment_status" in query else 1

    async def locked(_conn, _company, *ids):
        return {str(i): {"id": i, "status": "published", "starts_at": starts_at,
                         "timezone": None} for i in ids}

    async def no_conflicts(*_args, **_kwargs):
        return []

    async def approvable(_conn, _company, shift, employee_id, **kwargs):
        checked.append((shift["id"], employee_id, kwargs.get("exclude_shift_id")))
        if approvable_error:
            raise approvable_error

    async def noop(*_args, **_kwargs):
        return 1

    from app.workers.tasks import schedule_request_notifications as manager_worker
    monkeypatch.setattr(portal, "get_connection", _connection(Conn()))
    monkeypatch.setattr(shared, "fetch_locked_shift_pair", locked)
    monkeypatch.setattr("app.matcha.services.scheduling.shift_requests.find_same_day_assignments", no_conflicts)
    monkeypatch.setattr(manager, "assert_approvable", approvable)
    monkeypatch.setattr(shared, "log_audit", noop)
    monkeypatch.setattr(shared, "serialize_request", lambda row: row)
    monkeypatch.setattr("app.matcha.services.scheduling.employee_schedule_notifications.stage_request_event", noop)
    monkeypatch.setattr("app.matcha.services.scheduling.employee_schedule_notifications.dispatch_events", lambda: None)
    monkeypatch.setattr(manager_worker.send_schedule_request_notifications, "delay", lambda *_a: None)
    return SimpleNamespace(company_id=company_id, owner_id=owner_id, accepter_id=accepter_id,
                           shift_id=shift_id, counter_id=counter_id, request_id=request_id,
                           checked=checked)


@pytest.mark.asyncio
async def test_accepting_a_swap_checks_both_people_who_gain_a_shift(monkeypatch):
    env = _accept_env(monkeypatch, request_type="swap", starts_at=FUTURE)
    await portal.accept_schedule_request(
        env.request_id, CounterpartyAccept(), {"id": env.accepter_id, "org_id": env.company_id},
    )
    assert env.checked == [
        (env.shift_id, env.accepter_id, env.counter_id),
        (env.counter_id, env.owner_id, env.shift_id),
    ]


@pytest.mark.asyncio
async def test_accept_refuses_what_approval_could_not_force(monkeypatch):
    env = _accept_env(
        monkeypatch, request_type="pickup", starts_at=FUTURE,
        approvable_error=HTTPException(status_code=422, detail={"code": "location_mismatch"}),
    )
    with pytest.raises(HTTPException) as exc:
        await portal.accept_schedule_request(
            env.request_id, CounterpartyAccept(), {"id": env.accepter_id, "org_id": env.company_id},
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_accept_refuses_a_shift_that_already_started(monkeypatch):
    env = _accept_env(monkeypatch, request_type="pickup", starts_at=PAST)
    with pytest.raises(HTTPException) as exc:
        await portal.accept_schedule_request(
            env.request_id, CounterpartyAccept(), {"id": env.accepter_id, "org_id": env.company_id},
        )
    assert exc.value.status_code == 409
    assert "already started" in exc.value.detail
    assert env.checked == []


# ── Offers feed ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_offers_feed_is_store_scoped_and_hides_started_shifts(monkeypatch):
    company_id, employee_id, location_id = uuid4(), uuid4(), uuid4()
    seen = {}

    class Conn:
        async def fetch(self, query, *args):
            seen["query"], seen["args"] = query, args
            return []

    monkeypatch.setattr(portal, "get_connection", _connection(Conn()))
    result = await portal.list_schedule_offers(
        {"id": employee_id, "org_id": company_id, "work_location_id": location_id},
    )
    assert result == {"offers": []}
    assert "LEFT JOIN business_locations bl ON bl.id = s.location_id" in seen["query"]
    assert "s.starts_at > ((NOW() AT TIME ZONE COALESCE(bl.timezone, 'UTC'))" in seen["query"]
    assert "s.location_id IS NULL OR s.location_id = $3::uuid" in seen["query"]
    assert seen["args"] == (company_id, employee_id, location_id)


# ── Manager approval of a pickup ──────────────────────────────────────────────

def _review_env(monkeypatch, *, starts_at, request_type="pickup"):
    company_id, owner_id, accepter_id, shift_id, request_id = (uuid4() for _ in range(5))
    staged = []

    class Conn(_Tx):
        async def fetchrow(self, query, *_args):
            if "FROM schedule_requests WHERE id = $1 AND company_id = $2 FOR UPDATE" in query:
                return {"id": request_id, "company_id": company_id, "request_type": request_type,
                        "shift_id": shift_id, "employee_id": owner_id,
                        "target_employee_id": accepter_id, "counter_shift_id": None,
                        "counterparty_confirmed_at": NOW, "status": "awaiting_manager",
                        "proposed_availability": None, "availability_effective_on": None}
            return {"status": "approved"}

        async def fetchval(self, _query, *_args):
            return starts_at

        async def execute(self, *_args):
            return "UPDATE 1"

    async def locked(_conn, _company, *ids):
        return {str(i): {"id": i, "status": "published", "starts_at": starts_at,
                         "timezone": "America/Los_Angeles", "location_id": None} for i in ids}

    async def noop(*_args, **_kwargs):
        return True

    async def no_rows(*_args, **_kwargs):
        return []

    async def recipient(*_args, **_kwargs):
        return [], None

    async def stage(*_args, **kwargs):
        staged.append(kwargs)

    async def company(_user):
        return company_id

    monkeypatch.setattr(manager, "get_connection", _connection(Conn()))
    monkeypatch.setattr(manager, "require_company_id", company)
    monkeypatch.setattr(manager, "fetch_locked_shift_pair", locked)
    monkeypatch.setattr(manager, "lock_scheduling_employees", noop)
    monkeypatch.setattr(manager, "find_same_day_assignments", no_rows)
    monkeypatch.setattr(manager, "_check_recipient", recipient)
    monkeypatch.setattr(manager, "remove_assignment_core", noop)
    monkeypatch.setattr(manager, "apply_assignment_core", noop)
    monkeypatch.setattr(manager, "mark_manager_ready_notifications_resolved", noop)
    monkeypatch.setattr(manager, "log_audit", noop)
    monkeypatch.setattr(manager, "reconcile_warning_events", noop)
    monkeypatch.setattr(manager, "stage_request_event", stage)
    monkeypatch.setattr(manager, "dispatch_events", lambda: None)
    monkeypatch.setattr(manager, "serialize_request", lambda row: row)
    return SimpleNamespace(request_id=request_id, owner_id=owner_id, accepter_id=accepter_id,
                           staged=staged)


@pytest.mark.asyncio
async def test_pickup_decision_notifies_the_coworker_who_accepted(monkeypatch):
    env = _review_env(monkeypatch, starts_at=FUTURE)
    await manager.review_request(
        env.request_id, RequestReview(decision="approved"), SimpleNamespace(id=uuid4(), role="client"),
    )
    assert env.staged[0]["recipient_employee_ids"] == [env.owner_id, env.accepter_id]


@pytest.mark.asyncio
async def test_approval_refuses_a_pickup_whose_shift_already_started(monkeypatch):
    env = _review_env(monkeypatch, starts_at=PAST - timedelta(days=1))
    with pytest.raises(HTTPException) as exc:
        await manager.review_request(
            env.request_id, RequestReview(decision="approved", force=True), SimpleNamespace(id=uuid4(), role="client"),
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "Offered shift has already started"
    assert env.staged == []


# ── Withdraw / cancel ─────────────────────────────────────────────────────────

def _withdraw_env(monkeypatch, *, status, target):
    company_id, owner_id, request_id = uuid4(), uuid4(), uuid4()
    staged, dispatched = [], []

    class Conn(_Tx):
        async def fetchrow(self, query, *_args):
            if "WITH before AS" in query:
                return {"id": request_id, "updated_at": NOW, "prior_status": status,
                        "target_employee_id": target}
            return {"id": request_id, "employee_id": owner_id, "request_type": "pickup",
                    "target_employee_id": target, "status": status}

        async def fetchval(self, query, *_args):
            assert "RETURNING updated_at" in query
            return NOW

    async def noop(*_args, **_kwargs):
        return 0

    async def stage(*_args, **kwargs):
        staged.append(kwargs)

    monkeypatch.setattr(portal, "get_connection", _connection(Conn()))
    monkeypatch.setattr(shared, "log_audit", noop)
    monkeypatch.setattr(manager_notices, "mark_manager_ready_notifications_resolved", noop)
    monkeypatch.setattr("app.matcha.services.scheduling.employee_schedule_notifications.stage_request_event", stage)
    monkeypatch.setattr(
        "app.matcha.services.scheduling.employee_schedule_notifications.dispatch_events",
        lambda: dispatched.append(True),
    )
    return SimpleNamespace(company_id=company_id, owner_id=owner_id, request_id=request_id,
                           staged=staged, dispatched=dispatched)


@pytest.mark.asyncio
async def test_owner_withdrawing_an_accepted_offer_tells_the_coworker(monkeypatch):
    target = uuid4()
    env = _withdraw_env(monkeypatch, status="awaiting_manager", target=target)
    await portal.withdraw_schedule_request(env.request_id, {"id": env.owner_id, "org_id": env.company_id})
    assert len(env.staged) == 1
    assert env.staged[0]["recipient_employee_ids"] == [target]
    assert env.staged[0]["withdrawn_by"] == "owner"
    assert env.staged[0]["dedupe_key"].startswith(f"{env.request_id}:cancelled:")
    assert env.dispatched == [True]


@pytest.mark.asyncio
async def test_owner_withdrawing_an_unaccepted_offer_tells_nobody(monkeypatch):
    env = _withdraw_env(monkeypatch, status="awaiting_counterparty", target=None)
    await portal.withdraw_schedule_request(env.request_id, {"id": env.owner_id, "org_id": env.company_id})
    assert env.staged == [] and env.dispatched == []


@pytest.mark.asyncio
async def test_cancel_endpoint_tells_a_coworker_who_already_accepted(monkeypatch):
    target = uuid4()
    env = _withdraw_env(monkeypatch, status="awaiting_manager", target=target)
    result = await portal.cancel_my_schedule_request(
        env.request_id, {"id": env.owner_id, "org_id": env.company_id},
    )
    assert result["status"] == "cancelled"
    assert env.staged[0]["recipient_employee_ids"] == [target]
    assert env.staged[0]["withdrawn_by"] == "owner"
    assert env.dispatched == [True]


def test_withdrawn_notice_says_who_left():
    from app.matcha.services.scheduling.employee_schedule_notifications import _render

    owner_title, owner_body, _ = _render("schedule_request_withdrawn", {"withdrawn_by": "owner"})
    assert owner_title == "Shift request cancelled" and "cancelled the request you accepted" in owner_body
    title, body, _ = _render("schedule_request_withdrawn", {"withdrawn_by": "counterparty"})
    assert title == "Shift request withdrawn" and "withdrew from your request" in body


@pytest.mark.asyncio
async def test_reset_manager_ready_deliveries_clears_both_channels():
    seen = {}

    class Conn:
        async def execute(self, query, *args):
            seen["query"], seen["args"] = query, args
            return "DELETE 2"

    company_id, request_id = uuid4(), uuid4()
    assert await manager_notices.reset_manager_ready_deliveries(
        Conn(), company_id=company_id, request_id=request_id,
    ) == 2
    assert "'manager_ready', 'manager_ready_in_app'" in seen["query"]
    assert seen["args"] == (company_id, request_id)


# ── Duplicate offers and concurrent availability submits ─────────────────────

@pytest.mark.asyncio
async def test_repeat_pickup_offer_is_refused(monkeypatch):
    company_id, employee_id, shift_id = uuid4(), uuid4(), uuid4()

    class Conn(_Tx):
        async def fetchrow(self, query, *_args):
            assert "SELECT s.status" in query
            return {"status": "published"}

        async def fetchval(self, query, *args):
            assert "awaiting_counterparty" in query and args[2] == "pickup"
            return 1

    monkeypatch.setattr(portal, "get_connection", _connection(Conn()))
    with pytest.raises(HTTPException) as exc:
        await portal.create_my_schedule_request(
            ScheduleRequestCreate(request_type="pickup", shift_id=shift_id),
            {"id": employee_id, "org_id": company_id},
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "You already offered this shift"


@pytest.mark.asyncio
async def test_concurrent_availability_submit_is_a_409_not_a_500(monkeypatch):
    from datetime import time

    from app.matcha.models.scheduling.employee_schedule import AvailabilityReplace, AvailabilityWindow

    class Conn(_Tx):
        async def fetchval(self, query, *_args):
            query = " ".join(query.split())
            if "::date FROM employees e" in query:
                return date(2099, 1, 1)
            if "EXTRACT(DOW FROM s.starts_at)" in query or "FOR UPDATE" in query:
                return None
            if "INSERT INTO schedule_requests" in query:
                raise asyncpg.UniqueViolationError("uq_schedule_requests_open_availability")
            raise AssertionError(query)

    monkeypatch.setattr(portal, "get_connection", _connection(Conn()))
    body = AvailabilityChangeRequestCreate(
        availability=AvailabilityReplace(
            availability_state="windows",
            windows=[AvailabilityWindow(weekday=1, start_time=time(9), end_time=time(17))],
        ),
        effective_on=date(2099, 2, 1),
    )
    with pytest.raises(HTTPException) as exc:
        await portal.request_my_availability_change(body, {"id": uuid4(), "org_id": uuid4()})
    assert exc.value.status_code == 409


# ── Terminated employees ──────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("status_value,allowed", [("active", True), ("terminated", False),
                                                  ("offboarded", False), (None, False)])
async def test_schedule_surface_refuses_former_employees(monkeypatch, status_value, allowed):
    location_id = uuid4()

    class Conn:
        async def fetchrow(self, _query, *_args):
            if status_value is None:
                return None
            return {"employment_status": status_value, "work_location_id": location_id}

    monkeypatch.setattr(deps, "get_connection", _connection(Conn()))
    employee = {"id": uuid4(), "org_id": uuid4()}
    if allowed:
        result = await deps.require_schedulable_employee_record(employee)
        assert result["work_location_id"] == location_id and result["id"] == employee["id"]
    else:
        with pytest.raises(HTTPException) as exc:
            await deps.require_schedulable_employee_record(employee)
        assert exc.value.status_code == 403


def test_every_portal_schedule_route_uses_the_employment_gate():
    from tests._helpers.routes import iter_api_routes

    for route in iter_api_routes(portal.router):
        calls = {dep.call for dep in route.dependant.dependencies}
        assert deps.require_employee_record not in calls, route.path
        assert deps.require_schedulable_employee_record in calls, route.path


# ── Published-week guard and the store's calendar day ─────────────────────────

@pytest.mark.asyncio
async def test_published_week_guard_is_company_wide_without_an_employee():
    seen = {}

    class Conn:
        async def fetchval(self, query, *args):
            seen["query"], seen["args"] = query, args
            return False

    company_id = uuid4()
    assert await time_off_guard.has_published_schedule_week(
        Conn(), company_id, date(2099, 1, 1), date(2099, 1, 2),
    ) is False
    assert "work_location_id" not in seen["query"]
    assert seen["args"] == (company_id, date(2099, 1, 1), date(2099, 1, 2))


@pytest.mark.asyncio
async def test_employee_local_today_falls_back_to_database_date():
    answers = iter([None, date(2099, 3, 4)])

    class Conn:
        async def fetchval(self, _query, *_args):
            return next(answers)

    assert await time_off_guard.employee_local_today(Conn(), uuid4()) == date(2099, 3, 4)
