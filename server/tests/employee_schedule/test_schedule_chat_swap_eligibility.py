import asyncio
from datetime import datetime, timezone
from unittest import mock
from uuid import uuid4

from app.matcha.services.scheduling import schedule_chat


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class SwapConn:
    def __init__(self, first_shift, second_shift, first_employee, second_employee):
        self.shifts = {first_shift["id"]: first_shift, second_shift["id"]: second_shift}
        self.assignments = {
            first_shift["id"]: [{"employee_id": first_employee}],
            second_shift["id"]: [{"employee_id": second_employee}],
        }
        self.executed = []
        self.locked_shift_ids = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, shift_id, _company_id):
        assert "FROM schedule_shifts" in query
        return self.shifts.get(shift_id)

    async def fetchval(self, query, *_args):
        assert "pg_advisory_xact_lock" in query
        return None

    async def fetch(self, query, *args):
        if "FROM schedule_shifts" in query:
            self.locked_shift_ids = args[1]
            return [{"id": shift_id} for shift_id in args[1]]
        if "shift_id = ANY" in query:
            return [
                assignment
                for shift_id in args[0]
                for assignment in self.assignments[shift_id]
            ]
        shift_id = args[0]
        assert "schedule_shift_assignments" in query
        return self.assignments[shift_id]

    async def execute(self, query, *args):
        self.executed.append((query, args))


def _shift(shift_id, *, hour):
    return {
        "id": shift_id,
        "starts_at": datetime(2026, 8, 29, hour, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 8, 29, hour + 4, tzinfo=timezone.utc),
        "status": "published",
        "role": "Barista",
        "location_id": uuid4(),
        "job_id": None,
        "break_minutes": 0,
        "kind": "standard",
        "training_requirement_id": None,
        "published_at": datetime(2026, 8, 20, tzinfo=timezone.utc),
        "required_staff": 1,
    }


def test_huume_swap_checks_destination_eligibility_before_writes():
    company_id = uuid4()
    proposal_id = uuid4()
    first_id, second_id = uuid4(), uuid4()
    first_employee, second_employee = uuid4(), uuid4()
    first = _shift(first_id, hour=9)
    second = _shift(second_id, hour=14)
    conn = SwapConn(first, second, first_employee, second_employee)
    proposal_row = {
        "id": proposal_id,
        "company_id": company_id,
        "proposal": {"ops": [{
            "kind": "swap",
            "shift_id": str(first_id),
            "second_shift_id": str(second_id),
            "shift_role": "opener",
            "second_shift_role": "closer",
            "starts_at": first["starts_at"].isoformat(),
            "ends_at": first["ends_at"].isoformat(),
            "second_starts_at": second["starts_at"].isoformat(),
            "second_ends_at": second["ends_at"].isoformat(),
        }]},
    }

    async def eligibility_block(*_args, **kwargs):
        assert kwargs["employee_id"] == first_employee
        assert kwargs["location_id"] == second["location_id"]
        assert kwargs["exclude_shift_id"] == first_id
        return [{
            "check": "schedule_eligibility",
            "severity": "block",
            "message": "Food Handler Card expired 2025-01-10 and blocks new scheduling.",
        }]

    with (
        mock.patch.object(schedule_chat, "_claim_proposal_execution", mock.AsyncMock()),
        mock.patch.object(schedule_chat, "find_conflicts", mock.AsyncMock(return_value=[])),
        mock.patch.object(schedule_chat, "check_shift_compliance", side_effect=eligibility_block),
        mock.patch.object(schedule_chat, "remove_assignment_core", mock.AsyncMock()) as remove,
        mock.patch.object(schedule_chat, "apply_assignment_core", mock.AsyncMock()) as apply,
        mock.patch.object(schedule_chat, "log_audit", mock.AsyncMock()),
    ):
        result = asyncio.run(schedule_chat.execute_edit_proposal(
            conn,
            proposal_row=proposal_row,
            confirmed_by=uuid4(),
            features={},
        ))

    assert "Food Handler Card expired 2025-01-10" in result
    assert conn.locked_shift_ids == sorted([first_id, second_id])
    remove.assert_not_awaited()
    apply.assert_not_awaited()
