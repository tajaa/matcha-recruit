"""HR case triage is wired into incident creation and both close paths.

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_hooks.py -q
"""
import inspect
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests._helpers.routes import QueryConn


class DictRow(dict):
    """asyncpg Record stand-in that supports .get like the real one."""


@pytest.mark.asyncio
async def test_create_incident_core_queues_intake_triage():
    from app.matcha.services.hr_cases.triage import triage_incident_task
    from app.matcha.services.ir import ir_incident_create

    company = uuid4()
    incident_id = uuid4()
    row = DictRow(
        id=incident_id, incident_number="IR-1", title="Late again", status="reported",
        location_id=None, location=None, occurred_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
        reported_by_name="Sam", reported_by_email=None,
    )
    conn = QueryConn(fetchrow={"INSERT INTO ir_incidents": row, "FROM companies": {"name": "Po Coffee"}})
    _, bg_tasks = await ir_incident_create.create_incident_core(
        conn, company_id=str(company), description="Late again", occurred_at=None,
        reported_by_name="Sam", index_people=False,
    )
    triage = [t for t in bg_tasks if t[0] is triage_incident_task]
    assert triage == [(triage_incident_task, (str(incident_id), str(company)), {"phase": "intake"})]


def test_both_close_paths_schedule_the_close_check():
    from app.matcha.routes.ir_incidents import crud
    from app.matcha.services.ir import ir_copilot_flow

    assert "schedule_close_check(" in inspect.getsource(crud.update_incident)
    assert "schedule_close_check(" in inspect.getsource(ir_copilot_flow._close_incident_via_copilot)
