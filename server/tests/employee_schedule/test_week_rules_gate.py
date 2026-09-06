"""The week builder refuses until a location's week-set rules are established.

The failure this closes: a store with draft shifts and no saved profile got a
full generated week whose `operating_hours_known` was false — bounds nobody had
ever supplied, reported only in metrics nobody reads. Draft shifts are DEMAND;
they are not BOUNDS, so the gate runs before demand resolution.
"""

from datetime import date
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.matcha.services.scheduling import week_builder


COMPANY_ID = UUID("c0ffee00-0000-4000-8000-000000000001")
LOCATION_ID = UUID("c0ffee00-0000-4000-8000-000000000002")
OTHER_LOCATION_ID = UUID("c0ffee00-0000-4000-8000-000000000003")
RUN_ID = UUID("c0ffee00-0000-4000-8000-000000000004")
WEEK_START = date(2026, 8, 23)

FULL_WEEK_HOURS = {
    "0": None, "6": None,
    **{str(day): {"open": "08:00", "close": "17:00"} for day in range(1, 6)},
}


def _bundle(*, hours=None, blocks=True, leader_required=False):
    return {
        "profile": {
            "operating_hours": hours if hours is not None else FULL_WEEK_HOURS,
            "leader_job_id": None,
            "leader_required": leader_required,
        },
        "template": {"id": "t-1", "name": "Downtown default week",
                     "blocks": [{"name": "Opener"}] if blocks else []},
        "leader_job_name": None,
    }


FRESH_BUNDLE = {"profile": None, "template": None, "leader_job_name": None}


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    """Answers the reads on the way to the gate, and records every write so a
    test can assert nothing was persisted."""

    def __init__(self, *, row=None, scalar="Po Coffee Co — Downtown", rows=()):
        self.row = row
        self.scalar = scalar
        self.rows = list(rows)
        self.executed = []

    def transaction(self):
        return _AsyncContext(self)

    async def fetchrow(self, *_args):
        return self.row

    async def fetch(self, *_args):
        return self.rows

    async def fetchval(self, *_args):
        return self.scalar

    async def execute(self, *args):
        self.executed.append(args)


def _patch_bundle(monkeypatch, bundle):
    """Patched on `week_builder`, the module that DEFINES the caller — patching
    `location_profile` here would be a silent no-op."""
    loader = AsyncMock(return_value=bundle)
    monkeypatch.setattr(week_builder, "load_profile_bundle", loader)
    return loader


def _no_draft_persisted(conn) -> bool:
    return not any("schedule_generation_runs" in str(call[0]) for call in conn.executed)


@pytest.mark.asyncio
async def test_draft_shifts_without_a_saved_profile_still_refuse(monkeypatch):
    """The Po Coffee repro: 38 shifts on the grid, zero rows in
    `schedule_location_profiles`. Demand is not bounds."""
    conn = _FakeConn()
    monkeypatch.setattr(week_builder, "connection_or_direct", lambda: _AsyncContext(conn))
    monkeypatch.setattr(week_builder, "resolve_week_start_weekday", AsyncMock(return_value=0))
    _patch_bundle(monkeypatch, FRESH_BUNDLE)
    demand = AsyncMock(return_value=[{"key": "shift-1"}, {"key": "shift-2"}])
    monkeypatch.setattr(week_builder, "_load_existing_demand", demand)

    result = await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=WEEK_START,
    )

    assert result["status"] == "clarify"
    assert "Po Coffee Co — Downtown" in result["message"]
    assert result["setup_missing"] == ["operating_hours", "staffing_pattern", "leader_rule"]
    # Refused BEFORE demand resolution — the draft shifts were never even read.
    demand.assert_not_awaited()
    assert _no_draft_persisted(conn)


@pytest.mark.asyncio
async def test_partially_answered_hours_still_refuse(monkeypatch):
    """Hours for Monday and Tuesday leave the other five days unbounded."""
    conn = _FakeConn()
    monkeypatch.setattr(week_builder, "connection_or_direct", lambda: _AsyncContext(conn))
    monkeypatch.setattr(week_builder, "resolve_week_start_weekday", AsyncMock(return_value=0))
    _patch_bundle(monkeypatch, _bundle(hours={
        "1": {"open": "08:00", "close": "17:00"},
        "2": {"open": "08:00", "close": "17:00"},
    }))

    result = await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=WEEK_START,
    )

    assert result["status"] == "clarify"
    assert result["setup_missing"] == ["operating_hours"]
    assert _no_draft_persisted(conn)


@pytest.mark.asyncio
async def test_an_unanswered_leader_question_is_the_only_thing_missing(monkeypatch):
    """Hours and pattern saved, leader never asked — a single-answer refusal,
    which is what earns the Yes/No chips on the chat surface."""
    conn = _FakeConn()
    monkeypatch.setattr(week_builder, "connection_or_direct", lambda: _AsyncContext(conn))
    monkeypatch.setattr(week_builder, "resolve_week_start_weekday", AsyncMock(return_value=0))
    _patch_bundle(monkeypatch, _bundle(leader_required=None))

    result = await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=WEEK_START,
    )

    assert result["setup_missing"] == ["leader_rule"]


@pytest.mark.asyncio
async def test_established_rules_pass_the_gate(monkeypatch):
    conn = _FakeConn()
    _patch_bundle(monkeypatch, _bundle())

    gate = await week_builder._week_rules_gate(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID,
    )

    assert gate is None


@pytest.mark.asyncio
async def test_the_gate_reads_only_the_location_it_was_asked_about(monkeypatch):
    """One store's saved setup must never unblock another's — the whole point
    of a per-location profile."""
    bundles = {LOCATION_ID: _bundle(), OTHER_LOCATION_ID: FRESH_BUNDLE}
    seen = []

    async def load(_conn, *, company_id, location_id):
        seen.append(location_id)
        return bundles[location_id]

    monkeypatch.setattr(week_builder, "load_profile_bundle", load)
    conn = _FakeConn()

    assert await week_builder._week_rules_gate(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID,
    ) is None
    blocked = await week_builder._week_rules_gate(
        conn, company_id=COMPANY_ID, location_id=OTHER_LOCATION_ID,
    )

    assert blocked["status"] == "clarify"
    assert seen == [LOCATION_ID, OTHER_LOCATION_ID]


@pytest.mark.asyncio
async def test_confirming_a_proposal_re_checks_the_rules(monkeypatch):
    """Rules can be edited away in the Week setup pane between staging and
    approval, and the staged draft would still apply real shifts."""
    conn = _FakeConn(row={
        "id": RUN_ID, "location_id": LOCATION_ID, "week_start": WEEK_START,
        "status": "proposed", "source_mode": "existing", "week_template_id": None,
    })
    monkeypatch.setattr(week_builder, "connection_or_direct", lambda: _AsyncContext(conn))
    _patch_bundle(monkeypatch, FRESH_BUNDLE)
    snapshot = AsyncMock(side_effect=AssertionError("must not plan without rules"))
    monkeypatch.setattr(week_builder, "_planning_snapshot", snapshot)

    result = await week_builder.apply_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, generation_run_id=RUN_ID,
        location_id=LOCATION_ID, week_start=WEEK_START,
    )

    assert result["status"] == "error"
    assert "Po Coffee Co — Downtown" in result["message"]
    snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_readiness_reports_the_rule_blocker_first(monkeypatch):
    """Readiness saying "ready" and the builder then refusing is the loop this
    surface exists to end, so the two read the same predicate."""
    conn = _FakeConn(row={"id": LOCATION_ID, "name": "Po Coffee Co — Downtown"}, scalar=None)
    monkeypatch.setattr(week_builder, "connection_or_direct", lambda: _AsyncContext(conn))
    monkeypatch.setattr(week_builder, "resolve_week_start_weekday", AsyncMock(return_value=0))
    _patch_bundle(monkeypatch, FRESH_BUNDLE)
    monkeypatch.setattr(week_builder, "_load_roster_context", AsyncMock(return_value={
        "employees": [{
            "id": "employee-1", "name": "Amy", "availability_state": "windows",
            "target_weekly_minutes": 1200, "max_weekly_minutes": 2400,
        }],
    }))
    monkeypatch.setattr(week_builder, "_load_existing_demand", AsyncMock(return_value=[
        {"key": "shift-1", "required_staff": 2},
    ]))
    monkeypatch.setattr(
        week_builder, "_week_shift_counts", AsyncMock(return_value={"draft": 1, "published": 0}),
    )
    monkeypatch.setattr(week_builder, "_list_templates", AsyncMock(return_value=[]))
    monkeypatch.setattr(week_builder, "_load_week_shift_state", AsyncMock(return_value=[]))

    result = await week_builder.get_week_build_readiness(
        company_id=COMPANY_ID, location_id=LOCATION_ID, week_start=WEEK_START,
    )

    assert result["ready"] is False
    assert result["week_rules_missing"] == [
        "operating_hours", "staffing_pattern", "leader_rule",
    ]
    # First: it is the one blocker the manager can clear on their own, and the
    # only one the builder itself enforces.
    assert "I can't build this week yet" in result["blockers"][0]
