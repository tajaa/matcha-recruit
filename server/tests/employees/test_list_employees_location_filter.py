"""list_employees' work_location_id filter — SQL-construction only, no real
DB. Mirrors the existing `_InviteConn` fake-connection idiom in
tests/employees/test_employee_invites_and_compliance.py.

    cd server && ./venv/bin/python -m pytest tests/employees/test_list_employees_location_filter.py -q
"""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from app.core.models.auth import CurrentUser
from app.matcha.routes.employees import crud as employees_crud


def _run(coro):
    return asyncio.run(coro)


class _ListConn:
    """`fetch` on an information_schema query answers the various
    *_fields_available probes (always "yes"); `fetch` on anything else is
    the main SELECT — captured, not executed. `fetchval` answers
    _column_exists (also always "yes")."""

    def __init__(self):
        self.last_query = None
        self.last_params = None

    async def fetch(self, query, *params):
        q = " ".join(query.split())
        if "information_schema.columns" in q:
            # Whatever columns were asked about, say they all exist.
            return [{"column_name": "x"}]
        self.last_query = q
        self.last_params = params
        return []

    async def fetchval(self, query, *params):
        return True


def _fake_user():
    return CurrentUser(id=uuid4(), email="admin@example.com", role="client")


async def _list(monkeypatch, **kwargs):
    conn_holder = {}

    @asynccontextmanager
    async def _get_connection():
        conn = _ListConn()
        conn_holder["conn"] = conn
        yield conn

    async def _get_client_company_id(current_user):
        return uuid4()

    monkeypatch.setattr(employees_crud, "get_connection", _get_connection)
    monkeypatch.setattr(employees_crud, "get_client_company_id", _get_client_company_id)
    # Calling the route function directly (not through FastAPI) means every
    # other Query(...)-defaulted param must be overridden explicitly — the
    # Query sentinel objects are truthy, so left alone every filter branch
    # would fire.
    base = dict(
        status=None, employment_status=None, search=None, department=None,
        employment_type=None, work_state=None, work_city=None, manager_id=None,
        work_location_id=None,
    )
    base.update(kwargs)
    await employees_crud.list_employees(current_user=_fake_user(), **base)
    return conn_holder["conn"]


class TestWorkLocationIdFilter:
    def test_none_sentinel_filters_is_null_with_no_bound_param(self, monkeypatch):
        conn = _run(_list(monkeypatch, work_location_id="none"))
        assert "AND e.work_location_id IS NULL" in conn.last_query
        # No extra param bound for the sentinel — just company_id.
        assert len(conn.last_params) == 1

    def test_uuid_filters_by_equality_with_bound_param(self, monkeypatch):
        location_id = str(uuid4())
        conn = _run(_list(monkeypatch, work_location_id=location_id))
        assert "AND e.work_location_id = $" in conn.last_query
        assert location_id in conn.last_params

    def test_absent_adds_no_clause(self, monkeypatch):
        # work_location_id still appears in the SELECT list (every row's
        # location is always returned) — just not as a WHERE filter.
        conn = _run(_list(monkeypatch, work_location_id=None))
        assert "AND e.work_location_id" not in conn.last_query
