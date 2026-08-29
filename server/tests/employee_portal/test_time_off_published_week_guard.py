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
            assert "EXTRACT(DOW FROM s.starts_at)" in query
            assert args == (
                employee["org_id"], date(2099, 9, 10), date(2099, 9, 11),
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
