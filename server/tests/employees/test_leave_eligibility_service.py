from datetime import date, timedelta
from pathlib import Path
import sys
from uuid import uuid4

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import app.matcha.services.leave_eligibility_service as leave_eligibility_service_module
from app.matcha.services.leave_eligibility_service import LeaveEligibilityService


class _FakeConnContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _EligibilityConn:
    def __init__(self, *, employee_row, hours_row, company_count=60, rules=None):
        self.employee_row = employee_row
        self.hours_row = hours_row
        self.company_count = company_count
        self.rules = rules or []

    async def fetchrow(self, query, *args):
        if "FROM employees" in query:
            return self.employee_row
        if "FROM employee_hours_log" in query:
            return self.hours_row
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def fetchval(self, query, *args):
        if "SELECT COUNT(*) FROM employees" in query:
            return self.company_count
        raise AssertionError(f"Unexpected fetchval query: {query}")

    async def fetch(self, query, *args):
        if "FROM jurisdiction_requirements jr" in query:
            return self.rules
        raise AssertionError(f"Unexpected fetch query: {query}")


def _patch_connection(monkeypatch: pytest.MonkeyPatch, conn: _EligibilityConn):
    monkeypatch.setattr(leave_eligibility_service_module, "get_connection", lambda: _FakeConnContext(conn))


@pytest.mark.asyncio
async def test_check_fmla_eligibility_estimates_full_time_exempt_hours(monkeypatch: pytest.MonkeyPatch):
    conn = _EligibilityConn(
        employee_row={
            "id": uuid4(),
            "org_id": uuid4(),
            "start_date": date.today() - timedelta(days=500),
            "work_state": "CA",
            "employment_type": "full_time",
            "pay_classification": "exempt",
        },
        hours_row={"total_hours": 0, "entry_count": 0},
        company_count=75,
    )
    _patch_connection(monkeypatch, conn)

    result = await LeaveEligibilityService().check_fmla_eligibility(uuid4())

    assert result["eligible"] is True
    assert result["hours_worked_12mo"] == 2080.0
    assert result["hours_worked_12mo_source"] == "estimated"
    assert result["hours_worked_assumed_weekly"] == 40.0
    assert "40 hours/week" in result["hours_worked_note"]


@pytest.mark.asyncio
async def test_check_fmla_eligibility_prefers_logged_hours_over_estimate(monkeypatch: pytest.MonkeyPatch):
    conn = _EligibilityConn(
        employee_row={
            "id": uuid4(),
            "org_id": uuid4(),
            "start_date": date.today() - timedelta(days=500),
            "work_state": "CA",
            "employment_type": "full_time",
            "pay_classification": "exempt",
        },
        hours_row={"total_hours": 1000, "entry_count": 4},
        company_count=75,
    )
    _patch_connection(monkeypatch, conn)

    result = await LeaveEligibilityService().check_fmla_eligibility(uuid4())

    assert result["eligible"] is False
    assert result["hours_worked_12mo"] == 1000.0
    assert result["hours_worked_12mo_source"] == "logged"
    assert result["hours_worked_assumed_weekly"] is None
    assert any("1000 hours" in reason for reason in result["reasons"])


@pytest.mark.asyncio
async def test_check_state_programs_uses_estimated_hours_when_logs_missing(monkeypatch: pytest.MonkeyPatch):
    conn = _EligibilityConn(
        employee_row={
            "id": uuid4(),
            "org_id": uuid4(),
            "start_date": date.today() - timedelta(days=500),
            "work_state": "CA",
            "employment_type": "full_time",
            "pay_classification": "hourly",
        },
        hours_row={"total_hours": 0, "entry_count": 0},
        company_count=20,
        rules=[
            {
                "requirement_key": "ca_cfra",
                "title": "CA Family Rights Act (CFRA)",
                "description": (
                    '{"paid": false, "max_weeks": 12, "job_prot": true, '
                    '"emp_min": 5, "tenure_mo": 12, "hrs_min": 1250}'
                ),
                "current_value": None,
                "numeric_value": 12,
                "source_url": "https://example.com/cfra",
            }
        ],
    )
    _patch_connection(monkeypatch, conn)

    result = await LeaveEligibilityService().check_state_programs(uuid4())

    assert result["state"] == "CA"
    assert result["hours_worked_12mo"] == 1560.0
    assert result["hours_worked_12mo_source"] == "estimated"
    assert result["hours_worked_assumed_weekly"] == 30.0
    assert result["programs"][0]["eligible"] is True
    assert result["programs"][0]["reasons"] == ["Meets program requirements"]
