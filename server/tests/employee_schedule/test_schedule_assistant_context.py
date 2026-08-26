"""Regression tests for the bounded schedule-assistant read context.

These use a fake asyncpg connection deliberately: the repository's test
database is not safe for automatic DML, while the important contract here is
the shape of the bounded aggregate returned from the SQL reader.
"""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import schedule_assistant_context as context


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self, location, shifts):
        self.location = location
        self.shifts = shifts
        self.queries = []

    async def fetchrow(self, query, *params):
        self.queries.append(query)
        return self.location

    async def fetch(self, query, *params):
        self.queries.append(query)
        return self.shifts


@pytest.mark.asyncio
async def test_overview_caps_complete_shifts_and_excludes_cancelled_rows(monkeypatch):
    location_id = uuid4()
    company_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    conn = _Conn(
        {"id": location_id, "name": "Wilshire", "address": None, "city": "LA", "state": "CA", "zipcode": None},
        [{
            "id": shift_id,
            "role": "opener",
            "department": "front",
            "starts_at": datetime(2026, 8, 24, 8, tzinfo=timezone.utc),
            "ends_at": datetime(2026, 8, 24, 16, tzinfo=timezone.utc),
            "required_staff": 2,
            "status": "published",
            "kind": "regular",
            "notes": None,
            "total_shift_count": 501,
            "assignments": (
                '[{"employee_id": "' + str(employee_id) + '", "name": "A Employee", '
                '"status": "accepted", "manager_note": null, '
                '"manager_note_visible_to_employee": true, "compliance_guidance": null}]'
            ),
        }],
    )
    monkeypatch.setattr(context, "get_connection", lambda: _ConnectionContext(conn))

    result = await context.get_schedule_overview(
        company_id=company_id, location_id=location_id, week_start=date(2026, 8, 23),
    )

    assert result["shift_count"] == 1
    assert result["total_shift_count"] == 501
    assert result["truncated"] is True
    assert result["open_staffing_count"] == 1
    assert result["shifts"][0]["assignments"][0]["employee_id"] == str(employee_id)
    shift_query = conn.queries[1]
    assert "s.status <> 'cancelled'" in shift_query
    assert "json_agg" in shift_query
    assert "LIMIT 500" in shift_query


@pytest.mark.asyncio
async def test_overview_location_query_uses_real_business_locations_columns():
    """`business_locations` has no `postal_code` column — it's `zipcode`. The
    fake connection in the test above returns canned rows regardless of the
    query text, so it can't catch a column rename; this pins the SQL itself
    against the schema (see server/app/database/bootstrap/__init__.py) so a
    future rename fails loudly instead of 500ing every schedule-assistant
    overview call in production (2026-08-26 incident: exactly this)."""
    import inspect

    source = inspect.getsource(context.get_schedule_overview)
    assert "zipcode" in source
    assert "postal_code" not in source
