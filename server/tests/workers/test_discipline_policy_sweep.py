"""Discipline policy sweep — feature gate, briefing text, and the control flow
of `_run_discipline_policy_sweep` itself over a mock connection.

The pure halves (gate + briefing) are the parts that are wrong silently.
The control-flow class below covers the four claims the module docstring makes
that nothing else enforces: the scheduler gate, the NOT EXISTS ledger prefilter,
"checked and clean" stamping while a Gemini outage does NOT stamp, and the
thread-open unit rolling back when a concurrent run already stamped.

    cd server && ./venv/bin/python -m pytest tests/workers/test_discipline_policy_sweep.py -q
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.workers.tasks import discipline_policy_sweep as sweep
from app.workers.tasks.discipline_policy_sweep import (
    build_finding_briefing,
    discipline_policy_sweep_enabled,
)

CHECK_MOD = "app.matcha.services.discipline.discipline_policy_check"


def _incident(**over):
    base = {"incident_number": "IR-2026-07-0042", "title": "Needlestick in operatory 3"}
    base.update(over)
    return base


def _result(violations=None, summary="Likely sharps-handling violation."):
    return {"violations": violations if violations is not None else [], "summary": summary, "available": True}


def _violation(title="Sharps Handling", relevance="violated", confidence=0.9):
    return {"policy_title": title, "relevance": relevance, "confidence": confidence}


class TestDisciplinePolicySweepEnabled:
    def test_all_required_flags_true_enables(self):
        features = {
            "huume": True, "matcha_work": True, "discipline": True,
            "incidents": True, "handbooks": True,
        }
        assert discipline_policy_sweep_enabled(features, None) is True

    def test_missing_huume_disables(self):
        features = {"matcha_work": True, "discipline": True, "incidents": True, "handbooks": True}
        assert discipline_policy_sweep_enabled(features, None) is False

    def test_missing_handbooks_disables(self):
        # handbooks defaults True in DEFAULT_COMPANY_FEATURES, but an explicit
        # False (e.g. a tier override) must still gate the sweep off — it's
        # the corpus the policy check grounds on.
        features = {
            "huume": True, "matcha_work": True, "discipline": True,
            "incidents": True, "handbooks": False,
        }
        assert discipline_policy_sweep_enabled(features, None) is False

    def test_missing_incidents_disables(self):
        features = {"huume": True, "matcha_work": True, "discipline": True, "handbooks": True}
        assert discipline_policy_sweep_enabled(features, None) is False

    def test_resolved_via_merge_not_raw_lookup(self):
        # huume/discipline/incidents are all default-off; a company with only
        # the raw dict below (no explicit True) must resolve to disabled,
        # proving this goes through merge_company_features rather than
        # trusting caller-supplied dict keys directly.
        assert discipline_policy_sweep_enabled({}, "bespoke") is False


class TestBuildFindingBriefing:
    def test_states_incident_number_and_title(self):
        title, body = build_finding_briefing(_incident(), _result(violations=[_violation()]))
        assert "IR-2026-07-0042" in title
        assert "IR-2026-07-0042" in body
        assert "Needlestick in operatory 3" in body

    def test_singular_vs_plural_match_wording(self):
        _, one = build_finding_briefing(_incident(), _result(violations=[_violation()]))
        assert "1 possible match:" in one

        _, two = build_finding_briefing(_incident(), _result(violations=[_violation(), _violation(title="Bloodborne Pathogens")]))
        assert "2 possible matches:" in two

    def test_lists_up_to_five_violations_then_truncates(self):
        violations = [_violation(title=f"Policy {i}") for i in range(7)]
        _, body = build_finding_briefing(_incident(), _result(violations=violations))
        for i in range(5):
            assert f"Policy {i}" in body
        assert "Policy 5" not in body
        assert "…and 2 more" in body

    def test_includes_confidence_percentage(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation(confidence=0.87)]))
        assert "87%" in body

    def test_includes_summary_when_present(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation()], summary="A clear match."))
        assert "A clear match." in body

    def test_omits_summary_section_when_empty(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation()], summary=""))
        assert body.count("\n\n\n") == 0

    def test_invites_a_reply_to_draft_and_names_hr_approval(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation()]))
        assert "draft a disciplinary action" in body
        assert "HR approval" in body

    def test_never_states_a_verdict(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation()]))
        for banned in ("terminate", "you should discipline", "this is a violation of law"):
            assert banned not in body.lower()


# ── Control flow over a mock connection ──────────────────────────────────

ENABLED_FEATURES = {
    "huume": True, "matcha_work": True, "discipline": True,
    "incidents": True, "handbooks": True,
}


class _Txn:
    """Async context manager that records whether it exited with an exception —
    the only observable proof that the thread-open unit rolled back."""

    def __init__(self, log):
        self.log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.log.append(exc_type)
        return False


class _FakeConn:
    def __init__(self, scan_rows, *, stamp_returns=None):
        self.scan_rows = scan_rows
        self.queries: list[str] = []
        self.executed: list[tuple] = []
        self.txn_exits: list = []
        # fetchval answers, in order, for the INSERT ... RETURNING calls
        self.stamp_returns = list(stamp_returns or [])

    async def fetch(self, query, *args):
        self.queries.append(query)
        return self.scan_rows

    async def fetchval(self, query, *args):
        self.queries.append(query)
        if "INSERT INTO mw_threads" in query:
            return uuid4()
        if "discipline_policy_sweep_log" in query:
            return self.stamp_returns.pop(0) if self.stamp_returns else uuid4()
        return None

    async def execute(self, query, *args):
        self.queries.append(query)
        self.executed.append((query, args))

    def transaction(self):
        return _Txn(self.txn_exits)

    async def close(self):
        pass

    # -- assertions helpers
    def stamped_clean(self) -> bool:
        return any(
            "INSERT INTO discipline_policy_sweep_log" in q and "NULL, 0" in q
            for q, _ in self.executed
        )

    def any_ledger_write(self) -> bool:
        return any("discipline_policy_sweep_log" in q for q in self.queries if "INSERT" in q)


def _scan_row(**over):
    base = {
        "id": uuid4(), "company_id": uuid4(), "title": "Needlestick",
        "incident_number": "IR-1", "description": "d", "incident_type": "safety",
        "severity": "high", "enabled_features": dict(ENABLED_FEATURES),
        "signup_source": "bespoke",
    }
    base.update(over)
    return base


@pytest.fixture
def wire(monkeypatch):
    """Patch the worker's DB handle + scheduler gate, and the policy-check
    functions at the module that DEFINES them (the worker imports them inside
    the function body, so patching the worker module would be a no-op)."""
    def _wire(conn, *, enabled=True, max_per_cycle=25, check_result=None, check_raises=None):
        monkeypatch.setattr(sweep, "get_db_connection", AsyncMock(return_value=conn))
        row = None if enabled is None else {"enabled": enabled, "max_per_cycle": max_per_cycle}
        monkeypatch.setattr(sweep, "scheduler_settings_row", AsyncMock(return_value=row))
        check = AsyncMock(side_effect=check_raises) if check_raises else AsyncMock(
            return_value=check_result or {"violations": [], "summary": "", "available": True},
        )
        monkeypatch.setattr(f"{CHECK_MOD}.check_incident_against_handbook", check)
        monkeypatch.setattr(f"{CHECK_MOD}.persist_policy_check", AsyncMock(return_value=None))
        return check
    return _wire


class TestSweepControlFlow:
    @pytest.mark.asyncio
    async def test_skips_when_scheduler_disabled(self, wire):
        conn = _FakeConn([_scan_row()])
        check = wire(conn, enabled=False)
        result = await sweep._run_discipline_policy_sweep()
        assert result == {"skipped": True, "reason": "scheduler_disabled"}
        check.assert_not_awaited()
        assert conn.queries == []          # never even scanned

    @pytest.mark.asyncio
    async def test_skips_when_scheduler_row_absent(self, wire):
        conn = _FakeConn([])
        wire(conn, enabled=None)
        result = await sweep._run_discipline_policy_sweep()
        assert result == {"skipped": True, "reason": "scheduler_not_registered"}

    @pytest.mark.asyncio
    async def test_scan_sql_has_not_exists_ledger(self, wire):
        conn = _FakeConn([])
        wire(conn)
        await sweep._run_discipline_policy_sweep()
        scan = conn.queries[0]
        assert "NOT EXISTS" in scan
        assert "discipline_policy_sweep_log" in scan
        assert "i.status = 'closed'" in scan

    @pytest.mark.asyncio
    async def test_company_without_huume_is_skipped(self, wire):
        features = dict(ENABLED_FEATURES, huume=False)
        conn = _FakeConn([_scan_row(enabled_features=features)])
        check = wire(conn)
        await sweep._run_discipline_policy_sweep()
        check.assert_not_awaited()
        assert not conn.any_ledger_write()

    @pytest.mark.asyncio
    async def test_clean_incident_stamps_ledger_without_thread(self, wire):
        conn = _FakeConn([_scan_row()])
        wire(conn, check_result={"violations": [], "summary": "nothing", "available": True})
        result = await sweep._run_discipline_policy_sweep()
        assert result["checked"] == 1 and result["findings"] == 0 and result["threads_opened"] == 0
        assert conn.stamped_clean(), "a clean incident must be stamped or it is re-Gemini'd forever"
        assert not any("INSERT INTO mw_threads" in q for q in conn.queries)

    @pytest.mark.asyncio
    async def test_gemini_unavailable_does_not_stamp(self, wire):
        conn = _FakeConn([_scan_row()])
        wire(conn, check_result={"violations": [], "summary": "", "available": False})
        result = await sweep._run_discipline_policy_sweep()
        assert result["checked"] == 0
        assert not conn.any_ledger_write(), "an outage is not 'checked' — it must be retried"

    @pytest.mark.asyncio
    async def test_check_exception_does_not_stamp_and_does_not_abort_the_sweep(self, wire):
        conn = _FakeConn([_scan_row(), _scan_row()])
        wire(conn, check_raises=RuntimeError("gemini exploded"))
        result = await sweep._run_discipline_policy_sweep()
        assert result["checked"] == 0
        assert not conn.any_ledger_write()

    @pytest.mark.asyncio
    async def test_thread_open_is_single_transaction_with_stamp(self, wire):
        conn = _FakeConn([_scan_row()])
        wire(conn, check_result={
            "violations": [_violation()], "summary": "match", "available": True,
        })
        result = await sweep._run_discipline_policy_sweep()
        assert result["threads_opened"] == 1
        assert conn.txn_exits == [None], "thread + notifications + stamp must be ONE transaction"
        assert any("INSERT INTO mw_threads" in q for q in conn.queries)

    @pytest.mark.asyncio
    async def test_concurrent_stamp_rolls_the_thread_back(self, wire):
        # The ledger INSERT ... ON CONFLICT DO NOTHING RETURNING id yields None:
        # another run already delivered this incident.
        conn = _FakeConn([_scan_row()], stamp_returns=[None])
        wire(conn, check_result={
            "violations": [_violation()], "summary": "match", "available": True,
        })
        result = await sweep._run_discipline_policy_sweep()
        assert result["threads_opened"] == 0
        assert conn.txn_exits == [sweep._AlreadyStamped], "the whole unit must roll back"
