"""_match_single_employee's location-scoped-then-company-wide name
resolution — a bare first name ("swap Aisha's shift") should resolve
instantly when it's unique at the manager's current location, even if the
company has a same-named employee at a different location, and should only
ask for a last name when the ambiguity is real (two matches at the SAME
location, or no location context to narrow with). Fake asyncpg connection,
no real DB.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_employee_match.py -q
"""

import asyncio
from uuid import uuid4

from app.matcha.services.scheduling.schedule_chat import _match_single_employee


def _run(coro):
    return asyncio.run(coro)


def _employee(first, last, status="active"):
    return {"id": uuid4(), "first_name": first, "last_name": last, "employment_status": status}


class FakeConn:
    """Returns `scoped_rows` for a location-filtered query (one that binds
    work_location_id) and `unscoped_rows` for a company-wide one — mirrors
    _match_single_employee's two-pass search without a real DB."""

    def __init__(self, scoped_rows=None, unscoped_rows=None):
        self.scoped_rows = scoped_rows or []
        self.unscoped_rows = unscoped_rows if unscoped_rows is not None else (scoped_rows or [])
        self.queries: list[str] = []

    async def fetch(self, query, *params):
        self.queries.append(" ".join(query.split()))
        return self.scoped_rows if "work_location_id" in query else self.unscoped_rows


def test_unique_at_location_resolves_without_last_name():
    aisha_here = _employee("Aisha", "Khan")
    conn = FakeConn(scoped_rows=[aisha_here])
    result = _run(_match_single_employee(conn, "co1", "Aisha", uuid4()))
    assert result["employee"]["id"] == aisha_here["id"]
    assert len(conn.queries) == 1  # no fallback needed — resolved on the first pass


def test_multiple_at_location_still_clarifies_with_last_names():
    conn = FakeConn(scoped_rows=[_employee("Aisha", "Khan"), _employee("Aisha", "Patel")])
    result = _run(_match_single_employee(conn, "co1", "Aisha", uuid4()))
    assert result["ambiguous"] == ["Aisha Khan", "Aisha Patel"]


def test_no_match_at_location_falls_back_company_wide():
    aisha_elsewhere = _employee("Aisha", "Khan")
    conn = FakeConn(scoped_rows=[], unscoped_rows=[aisha_elsewhere])
    result = _run(_match_single_employee(conn, "co1", "Aisha", uuid4()))
    assert result["employee"]["id"] == aisha_elsewhere["id"]
    assert len(conn.queries) == 2


def test_no_location_known_searches_company_wide_directly():
    conn = FakeConn(unscoped_rows=[_employee("Aisha", "Khan")])
    result = _run(_match_single_employee(conn, "co1", "Aisha", None))
    assert "employee" in result
    assert len(conn.queries) == 1
    assert "work_location_id" not in conn.queries[0]


def test_full_name_hint_still_matches_a_compound_name():
    conn = FakeConn(scoped_rows=[_employee("John", "Henry")])
    result = _run(_match_single_employee(conn, "co1", "John Henry", uuid4()))
    assert result["employee"]["last_name"] == "Henry"


def test_inactive_employees_are_excluded():
    conn = FakeConn(scoped_rows=[_employee("Aisha", "Khan", status="terminated")])
    result = _run(_match_single_employee(conn, "co1", "Aisha", uuid4()))
    assert "none" in result
