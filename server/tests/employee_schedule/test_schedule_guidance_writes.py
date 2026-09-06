"""Write-boundary regressions for automatic assignment break minimums."""

import asyncio
import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
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


class _WeekConn:
    """The three reads `resolve_week_break_plans` makes, and nothing else."""

    def __init__(self, *, date_of_birth):
        self.date_of_birth = date_of_birth

    async def fetchval(self, _query, *_args):
        return "America/Los_Angeles"

    async def fetch(self, query, *_args):
        if "date_of_birth" in query:
            return [{"employee_id": EMPLOYEE_ID, "date_of_birth": self.date_of_birth}]
        return []


EMPLOYEE_ID = uuid4()


def _age_rule():
    from app.matcha.services.scheduling.schedule_breaks import BreakRule
    return BreakRule(
        rule_set_id=uuid4(), kind="meal", ordinal=1, trigger_after_minutes=300,
        duration_minutes=30, paid=False, deadline_offset_minutes=300,
        citation="Minor meal rule", maximum_age=17,
    )


def _resolved(rules):
    from types import SimpleNamespace
    return SimpleNamespace(
        rules=tuple(rules), source="catalog", advisories=(),
        timezone=None, rule_set_ids=(), rule_set_hash="hash",
    )


@pytest.mark.parametrize("date_of_birth, expect_advisory", [(None, True), (date(1990, 5, 1), False)])
def test_a_missing_date_of_birth_says_so_on_the_week_plan(
    monkeypatch, date_of_birth, expect_advisory,
):
    """The per-shift resolvers both append `employee_age_unverified`; the week
    resolver dropped it, so the only signal a manager got was a bare `error`."""
    monkeypatch.setattr(
        schedule_guidance, "resolve_break_rules",
        AsyncMock(return_value=_resolved([_age_rule()])),
    )
    conn = _WeekConn(date_of_birth=date_of_birth)
    shifts = [(
        "shift-1",
        datetime(2026, 9, 2, 9, tzinfo=timezone.utc),
        datetime(2026, 9, 2, 17, tzinfo=timezone.utc),
        [EMPLOYEE_ID],
    )]

    _tz, plans, unmapped = asyncio.run(schedule_guidance.resolve_week_break_plans(
        conn, uuid4(), location_id=uuid4(), shifts=shifts,
    ))

    plan = plans["shift-1"][EMPLOYEE_ID]
    codes = {item.get("code") for item in plan.advisories}
    assert ("employee_age_unverified" in codes) is expect_advisory
    # The date itself mapped fine — this is one person, not the jurisdiction.
    assert unmapped == set()
    assert (plan.status == "error") is expect_advisory
