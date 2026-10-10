"""Store managers on the schedule: who gets in, and what they can touch.

Business admins keep the company-wide behaviour they always had. An employee
flagged `is_manager`/`is_supervisor` manages only their own stores, never a
shift with no store, and never their own request. Every write refuses before
it reaches the database.
"""

from datetime import date, datetime, timezone
from inspect import getsource
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha import dependencies as deps
from app.matcha.models.scheduling.employee_schedule import (
    AssignmentCreate, AssignmentMove, PublishRange, RequestReview, ShiftCreate, ShiftUpdate,
)
from app.matcha.routes import employee_schedule
from app.matcha.routes.employee_schedule import (
    _shared, assignments, jobs, manager, requests, shifts,
)
from app.matcha.services.scheduling import labor_cost_service
from app.matcha.services.scheduling.schedule_manager_scope import (
    COMPANY_WIDE, ScheduleManagerScope, request_scope_sql, resolve_schedule_manager_scope,
)
from tests._helpers.routes import QueryConn, iter_api_routes

COMPANY_ID = uuid4()
USER_ID = uuid4()
EMPLOYEE_ID = uuid4()
OTHER_EMPLOYEE_ID = uuid4()
STORE_A = uuid4()
STORE_B = uuid4()
SHIFT_ID = uuid4()
REQUEST_ID = uuid4()

MANAGER = SimpleNamespace(id=USER_ID, role="employee")
CLIENT = SimpleNamespace(id=USER_ID, role="client")
MANAGER_ROWS = [{"id": EMPLOYEE_ID, "work_location_id": STORE_A, "manages": True}]
SCOPED = ScheduleManagerScope(
    company_wide=False, location_ids=frozenset({STORE_A}), actor_employee_ids=frozenset({EMPLOYEE_ID}),
)


class _Stop(Exception):
    """Raised by the fake once the query under test has been captured."""


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _Conn(QueryConn):
    """`QueryConn` plus transactions, and a needle that ends the handler."""

    def __init__(self, *, stop_on=None, **kwargs):
        super().__init__(**kwargs)
        self._stop_on = stop_on

    def transaction(self):
        return _Tx()

    def _dispatch(self, kind, sql, args):
        if self._stop_on and self._stop_on in sql:
            self.calls.append((kind, sql, args))
            raise _Stop
        return super()._dispatch(kind, sql, args)

    def wrote(self) -> bool:
        return any(
            word in sql for kind, sql, _ in self.calls if kind in ("execute", "fetchrow", "fetchval", "fetch")
            for word in ("INSERT ", "UPDATE schedule", "DELETE FROM")
        )


def _manager_conn(**kwargs):
    fetch = {"AS manages": MANAGER_ROWS, **kwargs.pop("fetch", {})}
    return _Conn(fetch=fetch, **kwargs)


@pytest.fixture
def wire(monkeypatch):
    def _wire(module, conn):
        monkeypatch.setattr(module, "get_connection", lambda: conn)
        monkeypatch.setattr(module, "require_company_id", AsyncMock(return_value=COMPANY_ID))
        return conn
    return _wire


# ── the scope itself ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "client", "individual"])
async def test_business_roles_are_company_wide_without_a_query(role):
    conn = _Conn()
    scope = await resolve_schedule_manager_scope(conn, company_id=COMPANY_ID, user=SimpleNamespace(id=USER_ID, role=role))
    assert scope is COMPANY_WIDE
    assert conn.calls == []


@pytest.mark.asyncio
async def test_an_employee_manager_is_scoped_to_their_stores_and_keeps_every_own_record():
    conn = _Conn(fetch={"AS manages": [
        *MANAGER_ROWS,
        {"id": OTHER_EMPLOYEE_ID, "work_location_id": STORE_B, "manages": False},
    ]})
    scope = await resolve_schedule_manager_scope(conn, company_id=COMPANY_ID, user=MANAGER)
    assert scope.company_wide is False
    assert scope.location_ids == {STORE_A}
    assert scope.actor_employee_ids == {EMPLOYEE_ID, OTHER_EMPLOYEE_ID}
    sql = conn.sql_for("fetch")[0]
    assert "is_manager" in sql and "is_supervisor" in sql and "employment_status" in sql
    assert conn.args_for("AS manages") == (COMPANY_ID, USER_ID)


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [
    SimpleNamespace(id=USER_ID, role="employee"),
    SimpleNamespace(id=USER_ID, role="candidate"),
    SimpleNamespace(id=USER_ID),
])
async def test_crew_other_roles_and_a_missing_role_are_refused(user):
    conn = _Conn(fetch={"AS manages": [{"id": EMPLOYEE_ID, "work_location_id": STORE_A, "manages": False}]})
    with pytest.raises(HTTPException) as exc:
        await resolve_schedule_manager_scope(conn, company_id=COMPANY_ID, user=user)
    assert exc.value.status_code == 403


def test_shift_rules_for_a_scoped_manager():
    SCOPED.assert_shift(STORE_A)
    COMPANY_WIDE.assert_shift(None)
    COMPANY_WIDE.assert_shift(STORE_B)
    with pytest.raises(HTTPException) as exc:
        SCOPED.assert_shift(None)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "unscoped_shift_read_only"
    with pytest.raises(HTTPException) as exc:
        SCOPED.assert_shift(STORE_B)
    assert exc.value.status_code == 404


def test_own_request_detection():
    assert SCOPED.is_own_request(EMPLOYEE_ID, None)
    assert SCOPED.is_own_request(OTHER_EMPLOYEE_ID, EMPLOYEE_ID)
    assert not SCOPED.is_own_request(OTHER_EMPLOYEE_ID, None)
    assert not COMPANY_WIDE.is_own_request(EMPLOYEE_ID, EMPLOYEE_ID)
    assert SCOPED.permits(STORE_A) and not SCOPED.permits(STORE_B) and not SCOPED.permits(None)


def test_request_scope_needs_every_store_the_request_touches():
    sql = request_scope_sql("$9::uuid[]")
    assert "e.work_location_id = ANY($9::uuid[])" in sql
    assert "r.shift_id IS NULL OR s.location_id = ANY($9::uuid[])" in sql
    assert "r.counter_shift_id IS NULL OR cs.location_id = ANY($9::uuid[])" in sql
    assert "r.target_employee_id IS NULL OR te.work_location_id = ANY($9::uuid[])" in sql


def test_queue_filter_is_unchanged_for_business_admins():
    params = [COMPANY_ID, "awaiting_manager"]
    assert _shared.request_queue_filter(COMPANY_WIDE, None, params) == ""
    assert params == [COMPANY_ID, "awaiting_manager"]
    clause = _shared.request_queue_filter(COMPANY_WIDE, STORE_B, params)
    assert clause == " AND COALESCE(s.location_id, e.work_location_id) = $3"
    assert params[-1] == STORE_B


def test_queue_filter_for_a_store_manager_excludes_their_own_requests_null_safely():
    params = [COMPANY_ID, "awaiting_manager"]
    clause = _shared.request_queue_filter(SCOPED, None, params)
    assert request_scope_sql("$3::uuid[]") in clause
    assert "NOT (r.employee_id = ANY($4::uuid[]))" in clause
    assert "NOT COALESCE(r.target_employee_id = ANY($4::uuid[]), false)" in clause
    assert params[2:] == [[STORE_A], [EMPLOYEE_ID]]


@pytest.mark.asyncio
async def test_store_check_for_business_admins_is_the_original_tenant_check():
    conn = _Conn(fetchrow={"FROM business_locations": None})
    await _shared.assert_store_in_scope(conn, COMPANY_ID, COMPANY_WIDE, None)
    assert conn.calls == []
    with pytest.raises(HTTPException) as exc:
        await _shared.assert_store_in_scope(conn, COMPANY_ID, COMPANY_WIDE, STORE_B)
    assert exc.value.status_code == 404
    assert "SELECT 1 FROM business_locations" in conn.sql_for("fetchrow")[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(("location", "row", "status"), [
    (None, {"is_active": True}, 403),
    (STORE_A, None, 404),
    (STORE_A, {"is_active": False}, 404),
    (STORE_B, {"is_active": True}, 403),
    (STORE_A, {"is_active": True}, None),
])
async def test_store_check_for_a_store_manager(location, row, status):
    conn = _Conn(fetchrow={"FROM business_locations": row})
    if status is None:
        await _shared.assert_store_in_scope(conn, COMPANY_ID, SCOPED, location)
        return
    with pytest.raises(HTTPException) as exc:
        await _shared.assert_store_in_scope(conn, COMPANY_ID, SCOPED, location)
    assert exc.value.status_code == status


# ── the route gate ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_gate(monkeypatch):
    conn = _Conn(fetchval={"FROM employees": True})
    monkeypatch.setattr(deps, "get_connection", lambda: conn)
    assert await deps.require_schedule_manager(CLIENT) is CLIENT
    assert conn.calls == []
    assert await deps.require_schedule_manager(MANAGER) is MANAGER
    assert conn.args_for("FROM employees") == (USER_ID,)

    conn.set("fetchval", "FROM employees", False)
    for user in (MANAGER, SimpleNamespace(id=USER_ID, role="candidate")):
        with pytest.raises(HTTPException) as exc:
            await deps.require_schedule_manager(user)
        assert exc.value.status_code == 403


MANAGER_ROUTES = {
    ("GET", "/week"),
    ("GET", "/locations/{location_id}/readiness"),
    ("POST", "/shifts"),
    ("PUT", "/shifts/{shift_id}"),
    ("DELETE", "/shifts/{shift_id}"),
    ("POST", "/shifts/{shift_id}/publish"),
    ("POST", "/shifts/publish"),
    ("GET", "/jobs"),
    ("POST", "/shifts/{shift_id}/assignments"),
    ("DELETE", "/shifts/{shift_id}/assignments/{employee_id}"),
    ("POST", "/assignments/move"),
    ("GET", "/requests"),
    ("POST", "/requests/{request_id}/review"),
}


def _route_deps(route):
    return {dep.call for dep in route.dependant.dependencies}


def test_exactly_the_manager_routes_admit_store_managers_and_each_resolves_its_scope():
    gated = {}
    for route in iter_api_routes(employee_schedule.router):
        if deps.require_schedule_manager in _route_deps(route):
            for method in route.methods:
                gated[(method, route.path)] = route.endpoint
    assert set(gated) == MANAGER_ROUTES
    for endpoint in gated.values():
        assert "resolve_schedule_manager_scope(" in getsource(endpoint), endpoint.__name__


def test_the_rest_of_the_package_keeps_its_own_gates():
    """A route moved onto the manager gate by accident would hand crew-adjacent
    accounts a write; every other route keeps the dependency it had."""
    for route in iter_api_routes(employee_schedule.router):
        route_deps = _route_deps(route)
        if deps.require_schedule_manager in route_deps:
            continue
        assert route_deps & {deps.require_admin_or_client, deps.require_company_member} or any(
            getattr(dep, "__name__", "") == "role_checker" for dep in route_deps
        ), route.path


# ── refusals at each endpoint, before any write ──────────────────────────────


@pytest.mark.asyncio
async def test_week_of_another_store_is_refused(wire):
    conn = wire(shifts, _manager_conn(fetchrow={"FROM business_locations": {"is_active": True}}))
    with pytest.raises(HTTPException) as exc:
        await shifts.get_week(start=date(2026, 10, 12), location=STORE_B, current_user=MANAGER)
    assert exc.value.status_code == 403
    assert not any("schedule_shifts" in sql for sql in conn.sql_for("fetch"))


@pytest.mark.asyncio
async def test_readiness_of_another_store_is_refused(wire):
    wire(shifts, _manager_conn(fetchrow={"FROM business_locations": {"is_active": True}}))
    with pytest.raises(HTTPException) as exc:
        await shifts.schedule_location_readiness(STORE_B, current_user=MANAGER)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_a_store_manager_cannot_create_a_shift_without_a_store(wire):
    conn = wire(shifts, _manager_conn())
    body = ShiftCreate(
        job_id=uuid4(),
        starts_at=datetime(2026, 10, 12, 9, tzinfo=timezone.utc),
        ends_at=datetime(2026, 10, 12, 17, tzinfo=timezone.utc),
    )
    with pytest.raises(HTTPException) as exc:
        await shifts.create_shift(body, force=False, current_user=MANAGER)
    assert exc.value.status_code == 403
    assert not conn.wrote()


def _shift_row(location_id):
    return {
        "starts_at": datetime(2026, 10, 12, 9, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 10, 12, 17, tzinfo=timezone.utc),
        "status": "draft", "published_at": None, "break_minutes": 30,
        "location_id": location_id, "role": "Barista", "department": None,
        "required_staff": 1, "color": None, "notes": None, "kind": "work",
        "training_requirement_id": None, "job_id": uuid4(), "updated_at": None,
        "id": SHIFT_ID, "assigned_count": 0, "timezone": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(("location", "status"), [(STORE_B, 404), (None, 403)])
async def test_editing_a_shift_outside_your_stores_is_refused(wire, location, status):
    conn = wire(shifts, _manager_conn(fetchrow={"FROM schedule_shifts WHERE id": _shift_row(location)}))
    with pytest.raises(HTTPException) as exc:
        await shifts.update_shift(SHIFT_ID, ShiftUpdate(notes="x"), force=False, current_user=MANAGER)
    assert exc.value.status_code == status
    assert not conn.wrote()


@pytest.mark.asyncio
async def test_moving_a_shift_to_another_store_is_refused(wire):
    conn = wire(shifts, _manager_conn(fetchrow={
        "FROM schedule_shifts WHERE id": _shift_row(STORE_A),
        "FROM business_locations": {"is_active": True},
    }))
    with pytest.raises(HTTPException) as exc:
        await shifts.update_shift(SHIFT_ID, ShiftUpdate(location_id=STORE_B), force=False, current_user=MANAGER)
    assert exc.value.status_code == 403
    assert not conn.wrote()


@pytest.mark.asyncio
async def test_deleting_another_stores_shift_is_refused_under_the_row_lock(wire):
    conn = wire(shifts, _manager_conn(fetchrow={"FROM schedule_shifts WHERE id": _shift_row(STORE_B)}))
    with pytest.raises(HTTPException) as exc:
        await shifts.delete_shift(SHIFT_ID, force=False, current_user=MANAGER)
    assert exc.value.status_code == 404
    assert "FOR UPDATE" in conn.sql_for("fetchrow")[0]
    assert not conn.wrote()


@pytest.mark.asyncio
async def test_publishing_another_stores_shift_is_refused(wire):
    conn = wire(shifts, _manager_conn(fetchrow={"FROM schedule_shifts": _shift_row(STORE_B)}))
    with pytest.raises(HTTPException) as exc:
        await shifts.publish_shift(SHIFT_ID, current_user=MANAGER)
    assert exc.value.status_code == 404
    assert not conn.wrote()


def _publish_body(location_id):
    start = datetime(2026, 10, 12, tzinfo=timezone.utc)
    return PublishRange(start=start, end=datetime(2026, 10, 19, tzinfo=timezone.utc), location_id=location_id)


@pytest.mark.asyncio
async def test_a_store_manager_must_publish_one_of_their_stores(wire):
    wire(shifts, _manager_conn())
    with pytest.raises(HTTPException) as exc:
        await shifts.publish_range(_publish_body(None), current_user=MANAGER)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("user", "includes_unscoped"), [(MANAGER, False), (CLIENT, True)])
async def test_publish_week_leaves_storeless_shifts_to_business_admins(wire, user, includes_unscoped):
    conn = wire(shifts, _manager_conn(
        fetchrow={"FROM business_locations": {"is_active": True}}, stop_on="status = 'draft'",
    ))
    with pytest.raises(_Stop):
        await shifts.publish_range(_publish_body(STORE_A), current_user=user)
    sql = next(sql for _kind, sql, _args in conn.calls if "status = 'draft'" in sql)
    assert "(location_id IS NULL AND $5::boolean)" in sql
    assert conn.args_for("status = 'draft'")[-1] is includes_unscoped


@pytest.mark.asyncio
async def test_assigning_on_another_stores_shift_is_refused(wire):
    conn = wire(assignments, _manager_conn(fetchrow={"FROM schedule_shifts s": _shift_row(STORE_B)}))
    with pytest.raises(HTTPException) as exc:
        await assignments.assign_employee(SHIFT_ID, AssignmentCreate(employee_id=OTHER_EMPLOYEE_ID),
                                          force=False, current_user=MANAGER)
    assert exc.value.status_code == 404
    assert not conn.wrote()


@pytest.mark.asyncio
async def test_unassigning_from_a_storeless_shift_is_refused(wire):
    conn = wire(assignments, _manager_conn(fetchrow={"FROM schedule_shifts s": _shift_row(None)}))
    with pytest.raises(HTTPException) as exc:
        await assignments.unassign_employee(SHIFT_ID, OTHER_EMPLOYEE_ID, force=False, current_user=MANAGER)
    assert exc.value.status_code == 403
    assert not conn.wrote()


@pytest.mark.asyncio
async def test_a_move_needs_both_shifts_in_scope(wire):
    target_id = uuid4()
    source = {**_shift_row(STORE_A), "id": SHIFT_ID}
    target = {**_shift_row(STORE_B), "id": target_id}
    conn = wire(assignments, _manager_conn(
        fetch={"FROM schedule_shifts s": [source, target]},
        fetchval={"pg_advisory_xact_lock": None},
    ))
    body = AssignmentMove(employee_id=OTHER_EMPLOYEE_ID, from_shift_id=SHIFT_ID, to_shift_id=target_id)
    with pytest.raises(HTTPException) as exc:
        await assignments.move_employee_assignment(body, force=False, current_user=MANAGER)
    assert exc.value.status_code == 404
    assert not conn.wrote()


@pytest.mark.asyncio
async def test_jobs_need_a_store_from_a_store_manager(wire):
    wire(jobs, _manager_conn())
    with pytest.raises(HTTPException) as exc:
        await jobs.list_jobs(location=None, current_user=MANAGER)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_jobs_return_only_the_listed_jobs_qualified_lists_and_no_rates(wire, monkeypatch):
    job_id = uuid4()
    conn = wire(jobs, _manager_conn(
        fetchrow={"FROM business_locations": {"is_active": True}},
        fetch={
            "FROM schedule_jobs": [{
                "id": job_id, "company_id": COMPANY_ID, "location_id": STORE_A, "name": "Barista",
                "color": None, "notes": None, "credential_grace_days": None,
                "default_hourly_rate": 21, "created_by": None, "created_at": None, "updated_at": None,
            }],
            "FROM schedule_job_employees": [{"job_id": job_id, "employee_id": OTHER_EMPLOYEE_ID}],
        },
    ))
    monkeypatch.setattr(jobs, "fetch_job_credential_requirements", AsyncMock(return_value=[]))
    result = await jobs.list_jobs(location=STORE_A, current_user=MANAGER)
    assert conn.args_for("FROM schedule_job_employees") == (COMPANY_ID, [job_id])
    assert result["jobs"][0]["employee_ids"] == [str(OTHER_EMPLOYEE_ID)]
    assert "default_hourly_rate" not in result["jobs"][0]


@pytest.mark.asyncio
async def test_wages_stay_with_business_admins():
    assert labor_cost_service.labor_cost_visible_from({"labor_cost": True}, "employee") is False
    assert await labor_cost_service.is_labor_cost_visible(COMPANY_ID, "employee") is False


# ── the request queue ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_store_managers_queue_is_their_stores_without_their_own_requests(wire):
    conn = wire(requests, _manager_conn(fetch={"FROM schedule_requests r": []}))
    await requests.list_requests(status=None, location=None, limit=50, current_user=MANAGER)
    sql = conn.sql_for("fetch")[-1]
    assert request_scope_sql("$3::uuid[]") in sql
    assert "NOT COALESCE(r.target_employee_id = ANY($4::uuid[]), false)" in sql
    assert conn.args_for("FROM schedule_requests r") == (COMPANY_ID, "awaiting_manager", [STORE_A], [EMPLOYEE_ID], 50)


@pytest.mark.asyncio
async def test_a_business_admin_can_narrow_the_queue_to_one_store(wire):
    conn = wire(requests, _Conn(
        fetchrow={"FROM business_locations": {"ok": 1}}, fetch={"FROM schedule_requests r": []},
    ))
    await requests.list_requests(status="approved", location=STORE_B, limit=10, current_user=CLIENT)
    sql = conn.sql_for("fetch")[-1]
    assert "COALESCE(s.location_id, e.work_location_id) = $3" in sql
    assert "ANY(" not in sql
    assert conn.args_for("FROM schedule_requests r") == (COMPANY_ID, "approved", STORE_B, 10)


@pytest.mark.asyncio
async def test_a_store_manager_cannot_filter_to_another_store(wire):
    wire(requests, _manager_conn(fetchrow={"FROM business_locations": {"is_active": True}}))
    with pytest.raises(HTTPException) as exc:
        await requests.list_requests(status=None, location=STORE_B, limit=50, current_user=MANAGER)
    assert exc.value.status_code == 403


def _request_row(employee_id, target=None, status="awaiting_manager"):
    return {
        "id": REQUEST_ID, "company_id": COMPANY_ID, "request_type": "drop", "shift_id": SHIFT_ID,
        "employee_id": employee_id, "target_employee_id": target, "counter_shift_id": None,
        "counterparty_confirmed_at": None, "status": status,
        "proposed_availability": None, "availability_effective_on": None,
    }


@pytest.mark.asyncio
async def test_reviewing_a_request_outside_your_stores_is_a_404(wire):
    conn = wire(requests, _manager_conn(
        fetchrow={"FROM schedule_requests WHERE id": _request_row(OTHER_EMPLOYEE_ID)},
        fetchval={"WHERE r.id = $1 AND": None},
    ))
    with pytest.raises(HTTPException) as exc:
        await requests.review_request(REQUEST_ID, RequestReview(decision="approved"), MANAGER)
    assert exc.value.status_code == 404
    assert conn.args_for("WHERE r.id = $1 AND") == (REQUEST_ID, [STORE_A])
    assert not conn.wrote()


@pytest.mark.asyncio
@pytest.mark.parametrize(("owner", "target"), [(EMPLOYEE_ID, None), (OTHER_EMPLOYEE_ID, EMPLOYEE_ID)])
async def test_a_store_manager_cannot_review_their_own_request(wire, owner, target):
    conn = wire(requests, _manager_conn(
        fetchrow={"FROM schedule_requests WHERE id": _request_row(owner, target)},
        fetchval={"WHERE r.id = $1 AND": 1},
    ))
    with pytest.raises(HTTPException) as exc:
        await requests.review_request(REQUEST_ID, RequestReview(decision="approved"), MANAGER)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "cannot_review_own_request"
    assert not conn.wrote()


@pytest.mark.asyncio
async def test_an_in_scope_request_reaches_the_ordinary_review_rules(wire):
    wire(requests, _manager_conn(
        fetchrow={"FROM schedule_requests WHERE id": _request_row(OTHER_EMPLOYEE_ID, status="denied")},
        fetchval={"WHERE r.id = $1 AND": 1},
    ))
    with pytest.raises(HTTPException) as exc:
        await requests.review_request(REQUEST_ID, RequestReview(decision="approved"), MANAGER)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "request_not_manager_ready"


@pytest.mark.asyncio
async def test_approval_rechecks_the_store_after_locking_the_shift(wire):
    conn = wire(requests, _manager_conn(
        fetchrow={"FROM schedule_requests WHERE id": _request_row(OTHER_EMPLOYEE_ID)},
        fetchval={"WHERE r.id = $1 AND": 1},
        # The shift moved to another store between the scope read and the lock.
        fetch={"FROM schedule_shifts s": [{**_shift_row(STORE_B), "status": "published"}]},
    ))
    with pytest.raises(HTTPException) as exc:
        await requests.review_request(REQUEST_ID, RequestReview(decision="approved"), MANAGER)
    assert exc.value.status_code == 404
    assert not conn.wrote()


@pytest.mark.asyncio
async def test_business_admin_review_skips_the_scope_query(wire):
    conn = wire(requests, _Conn(
        fetchrow={"FROM schedule_requests WHERE id": _request_row(OTHER_EMPLOYEE_ID, status="denied")},
    ))
    with pytest.raises(HTTPException) as exc:
        await requests.review_request(REQUEST_ID, RequestReview(decision="approved"), CLIENT)
    assert exc.value.status_code == 409
    assert conn.sql_for("fetchval") == []


# ── /manager/scope ───────────────────────────────────────────────────────────


@pytest.fixture
def features(monkeypatch):
    monkeypatch.setattr(manager, "get_company_features", AsyncMock(return_value={"huume": True, "labor_cost": True}))


@pytest.mark.asyncio
async def test_crew_learn_they_cannot_manage(wire, features):
    wire(manager, _Conn(fetch={"AS manages": []}))
    result = await manager.get_manager_scope(current_user=MANAGER)
    assert result["can_manage"] is False
    assert result["locations"] == [] and result["pending_requests"] == 0
    assert result["features"] == {"huume": True, "matcha_work": False, "time_off": False}


@pytest.mark.asyncio
async def test_a_store_manager_sees_their_stores_and_their_queue(wire, features):
    conn = wire(manager, _manager_conn(
        fetch={"FROM business_locations l": [
            {"id": STORE_A, "name": "Downtown", "timezone": "America/Los_Angeles", "week_start_weekday": 1},
        ]},
        fetchval={"SELECT COUNT(*)": 3},
    ))
    result = await manager.get_manager_scope(current_user=MANAGER)
    assert result == {
        "can_manage": True, "role": "employee", "company_wide": False,
        "locations": [{"id": str(STORE_A), "name": "Downtown", "timezone": "America/Los_Angeles",
                       "week_start_weekday": 1}],
        "features": {"huume": True, "matcha_work": False, "time_off": False},
        "pending_requests": 3,
    }
    assert conn.args_for("FROM business_locations l") == (COMPANY_ID, False, [STORE_A])
    assert request_scope_sql("$2::uuid[]") in conn.sql_for("fetchval")[0]
    assert "cost" not in str(result) and "rate" not in str(result)


@pytest.mark.asyncio
async def test_a_business_admin_sees_every_store(wire, features):
    conn = wire(manager, _Conn(
        fetch={"FROM business_locations l": []}, fetchval={"SELECT COUNT(*)": 0},
    ))
    result = await manager.get_manager_scope(current_user=CLIENT)
    assert result["company_wide"] is True
    assert conn.args_for("FROM business_locations l") == (COMPANY_ID, True, [])
    assert conn.args_for("SELECT COUNT(*)") == (COMPANY_ID,)
