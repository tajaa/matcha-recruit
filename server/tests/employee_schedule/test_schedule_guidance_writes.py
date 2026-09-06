"""Write-boundary regressions for automatic assignment break minimums."""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import schedule_guidance
from app.matcha.services.scheduling.schedule_breaks import BreakPlan, BreakRequirement


def _plan(minutes: int) -> BreakPlan:
    rule_set_id = uuid4()
    requirement = BreakRequirement(
        kind="meal", ordinal=1, duration_minutes=minutes, paid=False,
        earliest_local=None, recommended_local=None, deadline_local=None,
        waived=False, waiver_attestation_id=None, citation="", rule_set_id=rule_set_id,
    )
    return BreakPlan(
        status="complete", requirements=(requirement,), advisories=(),
        rule_set_ids=(rule_set_id,), rule_set_hash="hash",
    )


class Connection:
    def __init__(self, current_break: int):
        self.current_break = current_break
        self.updates = []
        self.audits = []

    async def fetchrow(self, query, *_args):
        assert "FOR UPDATE" in query
        starts_at = datetime(2026, 9, 2, 9, tzinfo=timezone.utc)
        return {
            "location_id": uuid4(), "starts_at": starts_at,
            "ends_at": datetime(2026, 9, 2, 17, tzinfo=timezone.utc),
            "break_minutes": self.current_break,
        }

    async def execute(self, query, *args):
        normalized = " ".join(query.split())
        if normalized.startswith("UPDATE schedule_shifts"):
            self.updates.append(args)
        elif normalized.startswith("INSERT INTO schedule_audit_log"):
            self.audits.append(json.loads(args[5]))
        else:
            raise AssertionError(f"unexpected execute: {normalized}")
        return "UPDATE 1"


@pytest.mark.parametrize(
    ("current_break", "expected_updates"),
    [(0, 1), (60, 0)],
    ids=["raises_low_break", "preserves_longer_break"],
)
def test_refresh_guidance_atomically_enforces_without_lowering(
    monkeypatch, current_break, expected_updates,
):
    plan = _plan(30)

    async def refresh(*_args, **_kwargs):
        return plan

    monkeypatch.setattr(schedule_guidance, "refresh_assignment_break_guidance", refresh)
    conn = Connection(current_break)
    result = asyncio.run(schedule_guidance.refresh_assignment_break_guidance_and_minimum(
        conn, uuid4(), shift_id=uuid4(), employee_id=uuid4(),
        actor_user_id=uuid4(), source="test",
    ))

    assert result == plan
    assert len(conn.updates) == expected_updates
    assert len(conn.audits) == expected_updates
    if expected_updates:
        assert conn.updates[0][0] == 30
        assert conn.audits[0]["source"] == "test"
