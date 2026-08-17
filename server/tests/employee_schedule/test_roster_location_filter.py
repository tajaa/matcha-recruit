"""fetch_roster's location scoping + assert_employee_schedulable_at — the
choke point that keeps a locationless employee out of both the roster and
off the assignment write paths. Fake asyncpg connection, no real DB.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_roster_location_filter.py -q
"""

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.routes.employee_schedule._shared import (
    assert_employee_schedulable_at,
    fetch_roster,
)


def _run(coro):
    return asyncio.run(coro)


class FakeConn:
    """Records the last query text (whitespace-collapsed) + params seen by
    `fetch`/`fetchrow`, and returns whatever the test pre-loads."""

    def __init__(self, fetch_rows=None, fetchrow_result=None):
        self.fetch_rows = fetch_rows or []
        self.fetchrow_result = fetchrow_result
        self.last_query = None
        self.last_params = None

    async def fetch(self, query, *params):
        self.last_query = " ".join(query.split())
        self.last_params = params
        return self.fetch_rows

    async def fetchrow(self, query, *params):
        self.last_query = " ".join(query.split())
        self.last_params = params
        return self.fetchrow_result


class TestFetchRosterLocationFilter:
    def test_no_location_id_is_back_compat_unfiltered(self):
        conn = FakeConn()
        _run(fetch_roster(conn, "co1"))
        assert "work_location_id" not in conn.last_query

    def test_location_id_filters_strictly_no_null_fallback(self):
        # fetch_shifts' location filter is `location_id = $N OR location_id
        # IS NULL` (a locationless SHIFT stays visible everywhere). The
        # roster is the opposite: a locationless EMPLOYEE must NOT show up
        # just because the filter is lenient — that's the whole point of
        # "no location -> not schedulable". Regression pin for the asymmetry.
        conn = FakeConn()
        location_id = uuid4()
        _run(fetch_roster(conn, "co1", location_id=location_id))
        assert "work_location_id = $3" in conn.last_query
        assert "IS NULL" not in conn.last_query
        assert location_id in conn.last_params


class TestAssertEmployeeSchedulableAt:
    def test_noop_when_shift_has_no_location(self):
        conn = FakeConn()
        _run(assert_employee_schedulable_at(conn, "co1", uuid4(), None))
        assert conn.last_query is None  # never even queried

    def test_422_when_employee_has_no_location(self):
        conn = FakeConn(fetchrow_result={"work_location_id": None})
        with pytest.raises(HTTPException) as exc:
            _run(assert_employee_schedulable_at(conn, "co1", uuid4(), uuid4()))
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "employee_has_no_location"

    def test_422_when_employee_missing_entirely(self):
        conn = FakeConn(fetchrow_result=None)
        with pytest.raises(HTTPException) as exc:
            _run(assert_employee_schedulable_at(conn, "co1", uuid4(), uuid4()))
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "employee_has_no_location"

    def test_422_on_location_mismatch(self):
        employee_loc = uuid4()
        shift_loc = uuid4()
        conn = FakeConn(fetchrow_result={"work_location_id": employee_loc})
        with pytest.raises(HTTPException) as exc:
            _run(assert_employee_schedulable_at(conn, "co1", uuid4(), shift_loc))
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "employee_wrong_location"

    def test_passes_on_match(self):
        location_id = uuid4()
        conn = FakeConn(fetchrow_result={"work_location_id": location_id})
        _run(assert_employee_schedulable_at(conn, "co1", uuid4(), location_id))  # no raise
