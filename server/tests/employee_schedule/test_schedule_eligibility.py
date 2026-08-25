import asyncio
from datetime import date
from uuid import uuid4

from app.matcha.services.scheduling.schedule_eligibility import (
    schedule_eligibility_roster_flags,
    schedule_eligibility_violations,
)


class FakeConn:
    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return [{"id": uuid4(), "status": "verified", "expires_at": date(2026, 8, 20),
                     "has_expiration": True, "label": "Food handler card",
                     "legal_basis": '{"citation": "Approved state rule"}'}]
        if "employee_work_permits" in query:
            return []
        raise AssertionError(query)


def test_expired_approved_schedule_blocking_credential_is_a_block():
    violations = asyncio.run(schedule_eligibility_violations(
        FakeConn(), uuid4(), employee_id=uuid4(), shift_date=date(2026, 8, 21),
    ))
    assert violations == [{
        "check": "schedule_eligibility", "severity": "block", "code": "credential_expired",
        "message": "Food handler card expired 2026-08-20 and blocks new scheduling.",
        "statute": "Approved state rule", "state": "",
    }]


class PendingCredentialConn:
    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return [{"id": uuid4(), "status": "pending", "expires_at": None,
                     "has_expiration": True, "label": "Food Handler Card",
                     "legal_basis": '{"citation": "Approved state rule"}'}]
        if "employee_work_permits" in query:
            return []
        raise AssertionError(query)


def test_missing_schedule_blocking_credential_blocks_immediately():
    violations = asyncio.run(schedule_eligibility_violations(
        PendingCredentialConn(), uuid4(), employee_id=uuid4(), shift_date=date(2026, 8, 21),
    ))
    assert violations[0]["code"] == "credential_missing"
    assert "approved credential document" in violations[0]["message"]


class ValidCredentialConn:
    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return [{"id": uuid4(), "status": "verified", "expires_at": date(2026, 8, 21),
                     "has_expiration": True, "label": "Food Handler Card",
                     "legal_basis": {"citation": "Approved state rule"}}]
        if "employee_work_permits" in query:
            return []
        raise AssertionError(query)


def test_credential_is_valid_through_its_expiration_date():
    violations = asyncio.run(schedule_eligibility_violations(
        ValidCredentialConn(), uuid4(), employee_id=uuid4(), shift_date=date(2026, 8, 21),
    ))
    assert violations == []


class MinorPermitConn:
    def __init__(self, permits):
        self.permits = permits

    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return []
        if "employee_work_permits" in query:
            return self.permits
        raise AssertionError(query)


def test_minor_without_a_current_location_permit_is_blocked():
    violations = asyncio.run(schedule_eligibility_violations(
        MinorPermitConn([]),
        uuid4(),
        employee_id=uuid4(),
        location_id=uuid4(),
        employee_age=17,
        shift_date=date(2026, 8, 21),
    ))
    assert violations == [{
        "check": "schedule_eligibility", "severity": "block", "code": "minor_work_permit_missing",
        "message": "A confirmed work permit is required before scheduling this minor at this location.",
        "statute": None, "state": "",
    }]


def test_minor_with_a_current_location_permit_is_allowed():
    violations = asyncio.run(schedule_eligibility_violations(
        MinorPermitConn([{
            "id": uuid4(), "location_id": uuid4(), "issued_at": date(2026, 1, 1),
            "expires_at": date(2026, 8, 21), "legal_basis": {},
        }]),
        uuid4(),
        employee_id=uuid4(),
        location_id=uuid4(),
        employee_age=16,
        shift_date=date(2026, 8, 21),
    ))
    assert violations == []


class RosterFlagConn:
    async def fetch(self, query, *args):
        assert "ANY($2::uuid[])" in query
        return [{"employee_id": args[1][0], "status": "pending", "expires_at": None,
                 "has_expiration": True, "warning_days": 14,
                 "label": "Food Handler Card", "legal_basis": {}}]


def test_roster_flags_expose_missing_blocking_credentials():
    employee_id = uuid4()
    flags = asyncio.run(schedule_eligibility_roster_flags(
        RosterFlagConn(), uuid4(), [employee_id], as_of=date(2026, 8, 21),
    ))
    assert flags[str(employee_id)]["blocking_credentials"] == [
        "Food Handler Card requires an approved credential document before scheduling."
    ]
