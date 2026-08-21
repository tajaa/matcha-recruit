import asyncio
from datetime import date
from uuid import uuid4

from app.matcha.services.scheduling.schedule_eligibility import schedule_eligibility_violations


class FakeConn:
    async def fetch(self, query, *args):
        if "employee_credential_requirements" in query:
            return [{"id": uuid4(), "due_date": date(2026, 8, 20), "label": "Food handler card",
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
