"""Shared writer and route contracts for employee scheduling profiles."""
from pathlib import Path
from uuid import UUID

import pytest

from app.matcha.models.scheduling.employee_schedule import (
    AvailabilityWindow, EmployeeJobAssignmentInput,
)
from app.matcha.services.scheduling import schedule_profiles

COMPANY = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EMPLOYEE = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ACTOR = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
JOB = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
LOCATION = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


class MissingProfileConn:
    def __init__(self):
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return None


@pytest.mark.asyncio
async def test_missing_profile_reads_unconfirmed_without_insert():
    conn = MissingProfileConn()
    profile = await schedule_profiles.fetch_schedule_profile(
        conn, company_id=COMPANY, employee_id=EMPLOYEE,
    )
    assert profile.availability_state == "unconfirmed"
    assert len(conn.calls) == 1
    assert "SELECT" in conn.calls[0][0]
    assert "INSERT" not in conn.calls[0][0]


class ProfileUpsertConn:
    def __init__(self):
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        if "INSERT INTO employee_schedule_profiles" not in sql:
            return None
        return {
            "availability_state": "always_available",
            "availability_confirmed_by": ACTOR,
        }


@pytest.mark.asyncio
async def test_profile_upsert_types_confirmation_parameters_as_uuid():
    conn = ProfileUpsertConn()
    profile = await schedule_profiles.upsert_schedule_profile(
        conn, company_id=COMPANY, employee_id=EMPLOYEE,
        values={"availability_state": "always_available"},
        actor_user_id=ACTOR,
    )
    insert_sql, args = conn.calls[1]
    assert "$13::uuid" in insert_sql
    assert "$5::uuid" in insert_sql
    assert args[12] == ACTOR
    assert profile.availability_confirmed_by == ACTOR


class ExecuteConn:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


@pytest.mark.asyncio
async def test_availability_replacement_confirms_state_through_one_core(monkeypatch):
    conn = ExecuteConn()
    captured = {}

    async def fake_upsert(_conn, **kwargs):
        captured.update(kwargs)
        return object()

    async def fake_audit(*args, **kwargs):
        captured["audited"] = True

    monkeypatch.setattr(schedule_profiles, "upsert_schedule_profile", fake_upsert)
    monkeypatch.setattr(schedule_profiles, "log_audit", fake_audit)
    window = AvailabilityWindow(weekday=1, start_time="09:00", end_time="17:00")
    result = await schedule_profiles.replace_availability_core(
        conn, company_id=COMPANY, employee_id=EMPLOYEE, windows=[window],
        availability_state=None, actor_user_id=ACTOR, actor_kind="admin",
    )
    assert result["state"] == "windows"
    assert captured["values"] == {"availability_state": "windows"}
    assert captured["audited"] is True
    assert "DELETE FROM schedule_employee_availability" in conn.executed[0][0]
    assert "INSERT INTO schedule_employee_availability" in conn.executed[1][0]


class JobsConn:
    def __init__(self, *, valid_location=True):
        self.valid_location = valid_location
        self.executed = []

    async def fetchval(self, sql, *args):
        return LOCATION

    async def fetch(self, sql, *args):
        if "SELECT id FROM schedule_jobs" in sql:
            return [{"id": JOB}] if self.valid_location else []
        if "qualification_status FROM schedule_job_employees" in sql:
            return []
        if "FROM schedule_job_employees je" in sql:
            return [{
                "job_id": JOB, "job_name": "Barista", "location_id": LOCATION,
                "is_primary": True, "qualification_status": "active",
                "qualified_from": None, "qualified_until": None, "notes": None,
            }]
        if "FROM schedule_job_credential_requirements" in sql:
            return []
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


@pytest.mark.asyncio
async def test_newly_active_job_materializes_credentials(monkeypatch):
    conn = JobsConn()
    materialized = []

    async def fake_materialize(_conn, **kwargs):
        materialized.append(kwargs)

    async def fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(schedule_profiles, "materialize_job_requirements", fake_materialize)
    monkeypatch.setattr(schedule_profiles, "log_audit", fake_audit)
    assignments = await schedule_profiles.replace_employee_jobs_core(
        conn, company_id=COMPANY, employee_id=EMPLOYEE,
        assignments=[EmployeeJobAssignmentInput(job_id=JOB, is_primary=True)],
        actor_user_id=ACTOR,
    )
    assert assignments[0]["job_name"] == "Barista"
    assert materialized == [{"company_id": COMPANY, "job_id": JOB, "employee_ids": [EMPLOYEE]}]


@pytest.mark.asyncio
async def test_location_scoped_job_must_match_employee_location():
    with pytest.raises(ValueError, match="work location"):
        await schedule_profiles.replace_employee_jobs_core(
            JobsConn(valid_location=False), company_id=COMPANY, employee_id=EMPLOYEE,
            assignments=[EmployeeJobAssignmentInput(job_id=JOB)], actor_user_id=ACTOR,
        )


def test_admin_and_portal_routes_share_the_same_availability_core():
    root = Path(__file__).parents[2] / "app/matcha/routes"
    admin = (root / "employee_schedule/availability.py").read_text()
    portal = (root / "employee_portal/schedule.py").read_text()
    assert "replace_availability_core(" in admin
    assert "replace_availability_core(" in portal


def test_job_centric_replace_preserves_retained_qualification_rows():
    route = Path(__file__).parents[2] / "app/matcha/routes/employee_schedule/jobs.py"
    source = route.read_text()
    assert "requested_ids - existing_ids" in source
    assert "existing_ids - requested_ids" in source
    assert "DELETE FROM schedule_job_employees" in source


def test_primary_unique_violation_is_a_clean_conflict():
    route = Path(__file__).parents[2] / "app/matcha/routes/employee_schedule/jobs.py"
    source = route.read_text()
    assert "except asyncpg.UniqueViolationError" in source
    assert 'status_code=409' in source


def test_combined_details_route_uses_one_caller_owned_transaction():
    route = Path(__file__).parents[2] / "app/matcha/routes/employee_schedule/availability.py"
    source = route.read_text()
    start = source.index('async def update_employee_scheduling_details(')
    body = source[start:]
    assert 'async with conn.transaction()' in body
    assert 'replace_employee_jobs_core(' in body
    assert 'replace_availability_core(' in body
    assert 'upsert_schedule_profile(' in body
