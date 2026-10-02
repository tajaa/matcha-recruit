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
        return dict(self.store) if self.store else None

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
        assert COMPANY_ID in args, "every store write is tenant-scoped"
        if "SET jurisdiction_id = NULL" in query:
            self.store["jurisdiction_id"] = None
            self.store["county"] = None
        elif "SET jurisdiction_id = $1, county = $2" in query:
            # The restore after a refused edit.
            self.store["jurisdiction_id"], self.store["county"] = args[0], args[1]
        elif "SET jurisdiction_id" in query:
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
    # Both: the repository refresh is its own route to the model (discovery +
    # research into the SHARED catalog) and defaults to on. Turning off only
    # live research still spent model calls for a scheduling-only tenant.
    assert task.kwargs == {
        "allow_live_research": has_compliance,
        "allow_repository_refresh": has_compliance,
    }


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
async def test_an_edit_that_does_not_move_the_store_keeps_its_jurisdiction(monkeypatch):
    conn = _Conn(jurisdiction_id=JURISDICTION_ID)
    _patch(monkeypatch, conn)
    monkeypatch.setattr(routes, "update_location", AsyncMock(return_value=SimpleNamespace()))
    resolver = AsyncMock()
    monkeypatch.setattr(routes, "_get_or_create_jurisdiction", resolver)
    tasks = BackgroundTasks()

    # A new name, a corrected street number, and the same city retyped.
    await routes.update_schedule_store(
        LOCATION_ID,
        ScheduleStoreUpdate(name="Downtown Flagship", address="2 Main", city=" austin ", state="tx", zipcode="78701"),
        tasks, _user(),
    )

    resolver.assert_not_awaited()
    assert conn.store["jurisdiction_id"] == JURISDICTION_ID
    assert "SET jurisdiction_id = NULL" not in conn.queries()
    assert tasks.tasks == []


def _moving_update(conn):
    """`update_location` stand-in that applies the new geography to the fake."""
    async def update(location_id, company_id, data):
        # The link is already gone by the time the geography changes: there is
        # no moment where the store sits in the new place under the old law.
        assert conn.store["jurisdiction_id"] is None
        conn.store.update(data.model_dump(exclude_unset=True))
        return SimpleNamespace(id=location_id)

    return update


@pytest.mark.asyncio
async def test_moving_a_store_relinks_it_to_where_it_now_is(monkeypatch):
    """Austin, TX corrected to Oakland, CA. Keeping the Texas jurisdiction left
    the store 'ready' and publishing under Texas break rules."""
    texas = JURISDICTION_ID
    california = UUID("44444444-4444-4444-4444-444444444444")
    conn = _Conn(jurisdiction_id=texas)
    conn.store["county"] = "Travis"
    _patch(monkeypatch, conn)
    monkeypatch.setattr(routes, "update_location", _moving_update(conn))
    resolver = AsyncMock(return_value=california)
    monkeypatch.setattr(routes, "_get_or_create_jurisdiction", resolver)
    tasks = BackgroundTasks()

    await routes.update_schedule_store(
        LOCATION_ID,
        ScheduleStoreUpdate(city="Oakland", state="CA", zipcode="94607", timezone="America/Los_Angeles"),
        tasks, _user(),
    )

    # Resolved from the NEW place, with the stale Texas county dropped.
    resolver.assert_awaited_once_with(conn, "Oakland", "CA", None, "94607")
    assert conn.store["jurisdiction_id"] == california
    assert [task.func for task in tasks.tasks] == [routes._project_store_compliance]


@pytest.mark.asyncio
async def test_a_failed_relink_leaves_the_store_unlinked_not_wrongly_ready(monkeypatch):
    conn = _Conn(jurisdiction_id=JURISDICTION_ID)
    _patch(monkeypatch, conn)
    monkeypatch.setattr(routes, "update_location", _moving_update(conn))
    monkeypatch.setattr(
        routes, "_get_or_create_jurisdiction", AsyncMock(side_effect=RuntimeError("resolver down")),
    )

    with pytest.raises(RuntimeError):
        await routes.update_schedule_store(
            LOCATION_ID, ScheduleStoreUpdate(city="Oakland", state="CA", zipcode="94607"),
            BackgroundTasks(), _user(),
        )

    # Fail closed: publishing is refused until the next save links it.
    assert conn.store["jurisdiction_id"] is None


@pytest.mark.asyncio
async def test_a_refused_move_puts_the_jurisdiction_back(monkeypatch):
    conn = _Conn(jurisdiction_id=JURISDICTION_ID)
    conn.store["county"] = "Travis"
    _patch(monkeypatch, conn)
    refused = HTTPException(status_code=422, detail="Select a valid IANA time zone")
    monkeypatch.setattr(routes, "update_location", AsyncMock(side_effect=refused))
    resolver = AsyncMock()
    monkeypatch.setattr(routes, "_get_or_create_jurisdiction", resolver)

    with pytest.raises(HTTPException) as caught:
        await routes.update_schedule_store(
            LOCATION_ID, ScheduleStoreUpdate(state="CA", timezone="Pacific"),
            BackgroundTasks(), _user(),
        )

    assert caught.value.status_code == 422
    # The store did not move, so a rejected request must not cost it its link.
    assert (conn.store["jurisdiction_id"], conn.store["county"]) == (JURISDICTION_ID, "Travis")
    resolver.assert_not_awaited()


def test_only_city_state_and_zip_count_as_a_move():
    before = {"city": "Austin", "state": "TX", "zipcode": "78701"}
    assert not routes._geography_changed(before, {"name": "X", "address": "9 Elm", "timezone": "America/Chicago"})
    assert not routes._geography_changed(before, {"city": "AUSTIN ", "state": "tx"})
    assert routes._geography_changed(before, {"zipcode": "78702"})
    assert routes._geography_changed(before, {"city": "Dallas"})
    assert not routes._geography_changed(None, {"city": "Dallas"})


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
