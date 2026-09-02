import asyncio
import inspect
from datetime import datetime, timezone
from unittest import mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.routes.employee_schedule import shifts


class PublishConn:
    def __init__(self, assignments):
        self.assignments = assignments
        self.query = ""

    async def fetch(self, query, *_args):
        self.query = query
        return self.assignments


def _shift(shift_id):
    return {
        "id": shift_id,
        "location_id": uuid4(),
        "job_id": None,
        "starts_at": datetime(2026, 8, 29, 9, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 8, 29, 17, tzinfo=timezone.utc),
        "break_minutes": 30,
        "kind": "standard",
        "training_requirement_id": None,
    }


def test_publish_gate_locks_assignments_and_blocks_expired_credentials():
    shift = _shift(uuid4())
    employee_id = uuid4()
    conn = PublishConn([{"shift_id": shift["id"], "employee_id": employee_id}])

    with (
        mock.patch.object(
            shifts, "_resolve_break_plans_for_ids",
            mock.AsyncMock(return_value=[object()]),
        ),
        mock.patch.object(shifts, "minimum_meal_break_minutes", return_value=30),
        mock.patch.object(
            shifts,
            "check_shift_compliance",
            mock.AsyncMock(return_value=[{
                "check": "schedule_eligibility",
                "severity": "block",
                "code": "credential_expired",
                "message": "Food Handler Card expired 2025-01-10 and blocks new scheduling.",
            }]),
        ) as check,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(shifts._lock_and_assert_publish_assignments_eligible(
                conn, uuid4(), [shift],
            ))

    assert exc.value.status_code == 422
    assert "FOR UPDATE" in conn.query
    assert check.await_args.kwargs["employee_id"] == employee_id
    assert check.await_args.kwargs["exclude_shift_id"] == shift["id"]


def test_publish_routes_lock_candidate_shifts_and_update_only_validated_ids():
    single_source = inspect.getsource(shifts.publish_shift)
    range_source = inspect.getsource(shifts.publish_range)

    assert "FOR UPDATE" in single_source
    assert "_lock_and_assert_publish_assignments_eligible" in single_source
    assert "FOR UPDATE" in range_source
    assert "_lock_and_assert_publish_assignments_eligible" in range_source
    assert "id = ANY($2::uuid[])" in range_source
