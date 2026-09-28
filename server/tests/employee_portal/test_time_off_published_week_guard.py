from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.employees.employee import PTORequestCreate
from app.matcha.routes.employee_portal import pto as portal_pto
from app.matcha.services.scheduling.time_off_guard import (
    PUBLISHED_WEEK_TIME_OFF_DETAIL,
)


@pytest.mark.asyncio
async def test_pto_request_rejects_a_week_with_published_shifts(monkeypatch):
    employee = {"id": uuid4(), "org_id": uuid4()}

    class Connection:
        async def fetchval(self, query, *args):
            if "::date" in query and "FROM employees e" in query:  # employee_local_today
                return date(2099, 9, 1)
            assert "EXTRACT(DOW FROM s.starts_at)" in query
            # Scoped to the employee's own store (and locationless shifts):
            # another store publishing its week must not block this request.
            assert "s.location_id IS NULL OR s.location_id = (" in query
            assert args == (
                employee["org_id"], date(2099, 9, 10), date(2099, 9, 11), employee["id"],
            )
            return True

    @asynccontextmanager
    async def fake_get_connection():
        yield Connection()

    monkeypatch.setattr(portal_pto, "get_connection", fake_get_connection)

    with pytest.raises(HTTPException) as exc_info:
        await portal_pto.submit_pto_request(
            PTORequestCreate(
                start_date=date(2099, 9, 10),
                end_date=date(2099, 9, 11),
                hours=Decimal("16"),
            ),
            employee,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == PUBLISHED_WEEK_TIME_OFF_DETAIL


@pytest.mark.asyncio
async def test_pto_past_date_is_judged_on_the_store_calendar(monkeypatch):
    """"Today" is the employee's store day, not the server's: UTC rolls over
    at 5 PM Pacific, and an evening request for today read as a past date."""
    employee = {"id": uuid4(), "org_id": uuid4()}
    store_today = date(2099, 9, 10)

    class Connection:
        async def fetchval(self, query, *args):
            assert "::date" in query and "FROM employees e" in query
            assert args == (employee["id"],)
            return store_today

    @asynccontextmanager
    async def fake_get_connection():
        yield Connection()

    monkeypatch.setattr(portal_pto, "get_connection", fake_get_connection)
    with pytest.raises(HTTPException) as exc_info:
        await portal_pto.submit_pto_request(
            PTORequestCreate(start_date=date(2099, 9, 9), end_date=date(2099, 9, 9),
                             hours=Decimal("8")),
            employee,
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cannot request PTO for past dates"
