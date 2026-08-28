"""Shift-date-effective job qualification gates."""
from datetime import date, datetime, timezone
from uuid import UUID

import pytest

from app.matcha.routes.employee_schedule._shared import check_job_qualification
from app.matcha.routes.employee_schedule._shared import fetch_roster
from app.matcha.services.scheduling.schedule_profiles import (
    fetch_effective_job_employee_ids,
)


COMPANY = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EMPLOYEE = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
JOB = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
STARTS_AT = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)


class QualificationConn:
    def __init__(self, *, qualified: bool = False):
        self.qualified = qualified
        self.sql = ""
        self.args = ()

    async def fetchrow(self, sql, *args):
        self.sql = sql
        self.args = args
        return {"name": "Barista", "qualified": self.qualified}

    async def fetch(self, sql, *args):
        self.sql = sql
        self.args = args
        return [{"employee_id": EMPLOYEE}] if self.qualified else []


@pytest.mark.asyncio
async def test_route_gate_uses_status_and_shift_date():
    conn = QualificationConn()
    detail = await check_job_qualification(
        conn, COMPANY, EMPLOYEE, JOB, starts_at=STARTS_AT,
    )
    assert detail["code"] == "not_qualified_for_job"
    assert "qualification_status = 'active'" in conn.sql
    assert "qualified_from" in conn.sql
    assert "qualified_until" in conn.sql
    assert conn.args[-1] == date(2026, 9, 15)


@pytest.mark.asyncio
async def test_batch_gate_returns_only_effective_members():
    conn = QualificationConn(qualified=True)
    result = await fetch_effective_job_employee_ids(
        conn, company_id=COMPANY, job_id=JOB,
        employee_ids=[EMPLOYEE], as_of=date(2026, 9, 15),
    )
    assert result == {EMPLOYEE}
    assert "qualification_status='active'" in conn.sql
    assert conn.args[-1] == date(2026, 9, 15)


@pytest.mark.asyncio
async def test_jobless_shift_remains_ungated_without_query():
    conn = QualificationConn()
    result = await fetch_effective_job_employee_ids(
        conn, company_id=COMPANY, job_id=None,
        employee_ids=[EMPLOYEE], as_of=date(2026, 9, 15),
    )
    assert result == {EMPLOYEE}
    assert conn.sql == ""


class RosterQualificationConn:
    def __init__(self):
        self.queries = []

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        if "FROM employees" in sql:
            return [{
                "id": EMPLOYEE, "first_name": "Aisha", "last_name": "Rivera",
                "job_title": "Manager", "department": None,
            }]
        return [{
            "employee_id": EMPLOYEE, "job_id": JOB,
            "qualified_from": date(2026, 9, 1),
            "qualified_until": date(2026, 9, 30),
            "currently_effective": False,
        }]


@pytest.mark.asyncio
async def test_roster_returns_active_qualification_windows_for_shift_date_preview():
    conn = RosterQualificationConn()
    roster = await fetch_roster(conn, COMPANY)

    assert "qualification_status = 'active'" in conn.queries[1]
    assert roster[0]["job_ids"] == []
    assert roster[0]["job_qualifications"] == [{
        "job_id": str(JOB),
        "qualified_from": "2026-09-01",
        "qualified_until": "2026-09-30",
    }]
