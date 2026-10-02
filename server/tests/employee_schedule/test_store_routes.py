"""Adding, repairing and staffing a store from the schedule screens."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from app.matcha.models.scheduling.employee_schedule import (
    ScheduleStoreAssignEmployees,
    ScheduleStoreCreate,
    ScheduleStoreUpdate,
)
from app.matcha.routes.employee_schedule import locations as routes
from app.matcha.services.scheduling.schedule_location_readiness import LocationReadiness

COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")
LOCATION_ID = UUID("66666666-6666-6666-6666-666666666666")
JURISDICTION_ID = UUID("33333333-3333-3333-3333-333333333333")
ACTOR_ID = UUID("77777777-7777-7777-7777-777777777777")


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class _Conn:
    """Just enough asyncpg to drive the store routes."""

    def __init__(self, *, jurisdiction_id=None, exists=True, assignable=()):
        self.store = {
            "id": LOCATION_ID, "name": "Downtown", "address": "1 Main", "city": "Austin",
            "state": "TX", "county": None, "zipcode": "78701", "is_active": True,
            "timezone": "America/Chicago", "jurisdiction_id": jurisdiction_id,
        } if exists else None
        self.assignable = set(assignable)
        self.calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        assert args[-1] == COMPANY_ID or COMPANY_ID in args, "every store read is tenant-scoped"
        return self.store

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        if "UPDATE employees" in query:
            return [{"id": employee_id} for employee_id in args[2] if employee_id in self.assignable]
        if "FROM employees" in query:
            return [{
                "id": uuid4(), "first_name": "Sam", "last_name": "Lee",
                "email": "sam@example.com", "job_title": "Barista", "work_state": "TX",
            }]
        raise AssertionError(query)

    async def execute(self, query, *args):
        self.calls.append((query, args))
        if "SET jurisdiction_id" in query:
            self.store["jurisdiction_id"] = args[0]
        return "UPDATE 1"

    def queries(self) -> str:
        return "\n".join(query for query, _ in self.calls)


def _patch(monkeypatch, conn, *, ready=True):
    monkeypatch.setattr(routes, "get_connection", lambda: _AsyncContext(conn))
    monkeypatch.setattr(routes, "require_company_id", AsyncMock(return_value=COMPANY_ID))
    monkeypatch.setattr(routes, "assert_manager_location", AsyncMock())
    monkeypatch.setattr(routes, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(routes, "get_schedule_location_readiness", AsyncMock(
        return_value=LocationReadiness(
            ready_to_publish=ready,
            missing_fields=() if ready else ("jurisdiction_id",),
            jurisdiction_id=JURISDICTION_ID if ready else None,
            timezone="America/Chicago",
            industry_code="722",
        ),
    ))


def _user():
    return SimpleNamespace(id=ACTOR_ID, role="client")


def _new_store(**overrides) -> ScheduleStoreCreate:
    values = {
        "name": " Downtown ", "address": "1 Main", "city": "Austin",
        "state": "tx", "zipcode": "78701", "timezone": "America/Chicago",
    }
    values.update(overrides)
    return ScheduleStoreCreate(**values)


def test_a_store_needs_its_whole_address():
    # Publishing requires address, city, state and zip, so a store cannot be
    # created half-filled and discovered unpublishable later.
    for missing in ("name", "address", "city", "state", "zipcode"):
        values = {"name": "N", "address": "1 Main", "city": "Austin", "state": "TX", "zipcode": "78701"}
        values.pop(missing)
        with pytest.raises(ValidationError):
            ScheduleStoreCreate(**values)
    with pytest.raises(ValidationError):
        _new_store(zipcode="7870")
    assert _new_store().name == "Downtown"
    with pytest.raises(ValidationError):
        ScheduleStoreAssignEmployees(employee_ids=[])


@pytest.mark.asyncio
async def test_create_goes_through_the_one_location_service(monkeypatch):
    conn = _Conn(jurisdiction_id=JURISDICTION_ID)
    _patch(monkeypatch, conn)
    create = AsyncMock(return_value=(SimpleNamespace(id=LOCATION_ID), True))
    monkeypatch.setattr(routes, "create_location", create)
    tasks = BackgroundTasks()

    result = await routes.create_schedule_store(_new_store(), tasks, _user())

    company_id, data = create.await_args.args
    assert company_id == COMPANY_ID
    assert (data.name, data.state, data.timezone, data.timezone_source) == (
        "Downtown", "TX", "America/Chicago", "manual",
    )
    assert result["id"] == str(LOCATION_ID)
    assert result["ready_to_publish"] is True
    # The shared catalog already covers this place: nothing to research.
    assert tasks.tasks == []
    routes.check_rate_limit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_infers_the_timezone_when_none_is_chosen(monkeypatch):
    conn = _Conn(jurisdiction_id=JURISDICTION_ID)
    _patch(monkeypatch, conn)
    create = AsyncMock(return_value=(SimpleNamespace(id=LOCATION_ID), True))
    monkeypatch.setattr(routes, "create_location", create)

    await routes.create_schedule_store(
        _new_store(state="CA", timezone=None), BackgroundTasks(), _user()
    )

    data = create.await_args.args[1]
    assert (data.timezone, data.timezone_source) == (None, "auto")


@pytest.mark.asyncio
@pytest.mark.parametrize("has_compliance", [True, False])
async def test_live_research_is_only_for_tenants_who_bought_compliance(monkeypatch, has_compliance):
    conn = _Conn(jurisdiction_id=JURISDICTION_ID)
    _patch(monkeypatch, conn)
    monkeypatch.setattr(
        routes, "create_location",
        AsyncMock(return_value=(SimpleNamespace(id=LOCATION_ID), False)),
    )
    monkeypatch.setattr(
        routes, "get_company_features", AsyncMock(return_value={"compliance": has_compliance}),
    )
    tasks = BackgroundTasks()

    await routes.create_schedule_store(_new_store(), tasks, _user())

    (task,) = tasks.tasks
    assert task.func is routes.run_compliance_check_background
    assert task.args == (LOCATION_ID, COMPANY_ID)
    assert task.kwargs == {"allow_live_research": has_compliance}


@pytest.mark.asyncio
async def test_editing_a_store_with_no_jurisdiction_links_one(monkeypatch):
    """The repair path for stores created before setup wrote a jurisdiction:
    without it the store can never publish, and no other screen sets it."""
    conn = _Conn(jurisdiction_id=None)
    _patch(monkeypatch, conn)
    update = AsyncMock(return_value=SimpleNamespace(id=LOCATION_ID))
    monkeypatch.setattr(routes, "update_location", update)
    resolver = AsyncMock(return_value=JURISDICTION_ID)
    monkeypatch.setattr(routes, "_get_or_create_jurisdiction", resolver)
    tasks = BackgroundTasks()

    result = await routes.update_schedule_store(
        LOCATION_ID, ScheduleStoreUpdate(timezone="America/Chicago", state="tx"), tasks, _user(),
    )

    routes.assert_manager_location.assert_awaited_once()
    location_id, company_id, data = update.await_args.args
    assert (location_id, company_id) == (LOCATION_ID, COMPANY_ID)
    assert data.model_dump(exclude_unset=True) == {"timezone": "America/Chicago", "state": "TX"}
    resolver.assert_awaited_once_with(conn, "Austin", "TX", None, "78701")
    assert conn.store["jurisdiction_id"] == JURISDICTION_ID
    assert "AND jurisdiction_id IS NULL" in conn.queries()
    assert [task.func for task in tasks.tasks] == [routes._project_store_compliance]
    assert result["timezone"] == "America/Chicago"


@pytest.mark.asyncio
async def test_a_store_that_has_a_jurisdiction_keeps_it(monkeypatch):
    conn = _Conn(jurisdiction_id=JURISDICTION_ID)
    _patch(monkeypatch, conn)
    monkeypatch.setattr(routes, "update_location", AsyncMock(return_value=SimpleNamespace()))
    resolver = AsyncMock()
    monkeypatch.setattr(routes, "_get_or_create_jurisdiction", resolver)
    tasks = BackgroundTasks()

    await routes.update_schedule_store(
        LOCATION_ID, ScheduleStoreUpdate(city="Dallas"), tasks, _user(),
    )

    resolver.assert_not_awaited()
    assert tasks.tasks == []


@pytest.mark.asyncio
async def test_an_empty_edit_still_repairs_and_a_missing_store_is_a_404(monkeypatch):
    conn = _Conn(jurisdiction_id=None)
    _patch(monkeypatch, conn)
    update = AsyncMock()
    monkeypatch.setattr(routes, "update_location", update)
    monkeypatch.setattr(routes, "_get_or_create_jurisdiction", AsyncMock(return_value=JURISDICTION_ID))

    await routes.update_schedule_store(LOCATION_ID, ScheduleStoreUpdate(), BackgroundTasks(), _user())
    update.assert_not_awaited()
    assert conn.store["jurisdiction_id"] == JURISDICTION_ID

    gone = _Conn(exists=False)
    _patch(monkeypatch, gone)
    monkeypatch.setattr(routes, "update_location", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as caught:
        await routes.update_schedule_store(
            LOCATION_ID, ScheduleStoreUpdate(name="X"), BackgroundTasks(), _user(),
        )
    assert caught.value.status_code == 404
    with pytest.raises(HTTPException) as caught:
        await routes._store_payload(gone, COMPANY_ID, LOCATION_ID)
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_assigning_only_places_employees_who_have_no_store(monkeypatch):
    free, elsewhere = uuid4(), uuid4()
    conn = _Conn(assignable=[free])
    _patch(monkeypatch, conn)

    result = await routes.assign_employees_to_store(
        LOCATION_ID, ScheduleStoreAssignEmployees(employee_ids=[free, elsewhere]), _user(),
    )

    assert result == {"assigned": [str(free)], "skipped": [str(elsewhere)]}
    routes.assert_manager_location.assert_awaited_once()
    query, args = next(call for call in conn.calls if "UPDATE employees" in call[0])
    assert args[:2] == (LOCATION_ID, COMPANY_ID)
    # Tenant-scoped, add-only: never moves someone off another store.
    assert "org_id = $2" in query
    assert "work_location_id IS NULL" in query


@pytest.mark.asyncio
async def test_unassigned_employees_are_listed_for_the_callers_company(monkeypatch):
    conn = _Conn()
    _patch(monkeypatch, conn)

    result = await routes.list_unassigned_employees(_user())

    assert result["employees"][0]["email"] == "sam@example.com"
    query, args = conn.calls[-1]
    assert args == (COMPANY_ID,)
    assert "work_location_id IS NULL" in query


@pytest.mark.asyncio
async def test_projection_never_researches_and_never_raises(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(routes, "run_compliance_check_background", check)
    await routes._project_store_compliance(LOCATION_ID, COMPANY_ID)
    assert check.await_args.kwargs == {
        "check_type": "proactive",
        "allow_live_research": False,
        "allow_repository_refresh": False,
    }
    monkeypatch.setattr(
        routes, "run_compliance_check_background", AsyncMock(side_effect=RuntimeError("down")),
    )
    await routes._project_store_compliance(LOCATION_ID, COMPANY_ID)
