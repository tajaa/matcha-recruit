"""The assignment guard inside schedule_chat — stage-time split into staged /
not-staged, the fail-closed jurisdiction gate, and the confirm-time copy for
an overlap Huume itself created. Fakes only; no DB.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_guard_integration.py -q
"""

import asyncio
from datetime import datetime, timezone
from unittest import mock
from uuid import UUID, uuid4

from app.matcha.services.scheduling import schedule_chat

UTC = timezone.utc
COMPANY = UUID("11111111-1111-1111-1111-111111111111")
USER = UUID("22222222-2222-2222-2222-222222222222")
DANA = "33333333-3333-3333-3333-000000000001"
CURATED = {"state": "CA", "status": "curated", "message": "Scheduling law for CA is on file (hand-curated)."}
UNMAPPED = {"state": "TX", "status": "unmapped",
            "message": "Legality was NOT verified for TX — Matcha has no researched scheduling thresholds for it. "
                       "Confirming means you've checked meal-break, overtime and rest rules yourself."}
UNAVAILABLE = {"state": "TX", "status": "unavailable",
               "message": "Could not load TX's scheduling-law thresholds just now — this is temporary, not an all-clear."}


def _run(coro):
    return asyncio.run(coro)


def _op(index, *, verdict="ok", reasons=(), shift_id=None, start=(23, 6), end=(23, 14)):
    starts = datetime(2026, 8, start[0], start[1], tzinfo=UTC)
    ends = datetime(2026, 8, end[0], end[1], tzinfo=UTC)
    return {
        "kind": "assign", "shift_id": shift_id or f"s{index}", "second_shift_id": None,
        "second_shift_role": None, "second_starts_at": None, "second_ends_at": None,
        "shift_role": "shift lead", "starts_at": starts.isoformat(), "ends_at": ends.isoformat(),
        "location_id": None, "break_minutes": 0, "shift_kind": "work", "training_requirement_id": None,
        "from_employee_id": None, "from_employee_name": None,
        "to_employee_id": DANA, "to_employee_name": "Dana Reyes",
        "new_starts_at": None, "new_ends_at": None, "advisories": [],
        "review": {"verdict": verdict, "reasons": list(reasons),
                   "before": {"minutes": 0, "shifts": 0, "days": 0},
                   "after": {"minutes": 480, "shifts": 1, "days": 1}},
    }


class _PersistConn:
    async def fetchval(self, *_a, **_k):
        return None

    async def fetchrow(self, *_a, **_k):
        return {"id": UUID("44444444-4444-4444-4444-444444444444")}


def _build(ops, jurisdiction):
    persisted = {}

    async def fake_resolve(conn, **kwargs):
        return ops

    async def fake_jurisdiction(conn, company_id, ops_, location_id):
        return dict(jurisdiction)

    async def fake_persist(conn, existing_id, **kwargs):
        persisted.update(kwargs)
        return UUID("44444444-4444-4444-4444-444444444444")

    with (
        mock.patch.object(schedule_chat, "_resolve_edit_ops", fake_resolve),
        mock.patch.object(schedule_chat, "_ops_jurisdiction", fake_jurisdiction),
        mock.patch.object(schedule_chat, "_persist_proposal", fake_persist),
    ):
        build = _run(schedule_chat.build_edit_proposal(
            _PersistConn(), company_id=COMPANY, channel_id=None, source_message_id=None,
            created_by=USER, parsed={"ack": "Got it.", "edit_requests": []}, today=datetime(2026, 8, 20).date(),
            original_content="[huume thread] assign request", surface="editor",
        ))
    return build, persisted


class TestBuildEditProposalSplit:
    def test_blocked_ops_are_removed_and_listed_not_staged(self):
        blocked = _op(1, verdict="blocked", start=(23, 10), end=(23, 18),
                      reasons=[{"code": "intra_batch_overlap", "policy": False,
                                "message": "would overlap the Shift Lead Sun Aug 23 06:00–14:00 shift earlier in this batch"}])
        build, persisted = _build([_op(0), blocked, _op(2, start=(24, 6), end=(24, 14))], CURATED)
        assert build.kind == "proposal"
        doc = persisted["proposal"]
        assert [op["shift_id"] for op in doc["ops"]] == ["s0", "s2"]
        assert [item["shift_id"] for item in doc["rejected"]] == ["s1"]
        assert doc["compliance_status"] == "verified"
        assert doc["review"]["rejected"][0]["reasons"][0]["code"] == "intra_batch_overlap"
        assert build.review["proposal_id"] == "44444444-4444-4444-4444-444444444444"
        assert "**Not staged** (1)" in build.pill_text
        assert "earlier in this batch" in build.pill_text
        assert "Reply **confirm** and I'll make these changes" in build.pill_text

    def test_policy_warnings_render_on_staged_ops(self):
        warned = _op(0, verdict="warn", reasons=[{"code": "rest_gap", "policy": True,
                                                  "message": "only 0.0h rest next to another shift (policy: 8h minimum)"}])
        build, _ = _build([warned], CURATED)
        assert "⚠ Dana Reyes: only 0.0h rest" in build.pill_text

    def test_all_blocked_is_a_refused_clarify_with_reasons(self):
        blocked = _op(0, verdict="blocked", reasons=[{"code": "existing_overlap", "policy": False,
                                                      "message": "already on the Opener Sun Aug 23 08:00–16:00 shift"}])
        build, persisted = _build([blocked], CURATED)
        assert build.kind == "clarify" and build.clarify_kind == "refused"
        assert persisted["status"] == "clarifying"
        assert "couldn't stage any of those" in build.pill_text
        assert "already on the Opener" in build.pill_text

    def test_unmapped_state_stages_with_the_honesty_line(self):
        build, persisted = _build([_op(0)], UNMAPPED)
        assert build.kind == "proposal"
        assert persisted["proposal"]["compliance_status"] == "unmapped"
        assert "NOT verified for TX" in build.pill_text
        assert "confirm** to make these changes anyway" in build.pill_text

    def test_unavailable_rules_refuse_to_stage(self):
        build, persisted = _build([_op(0)], UNAVAILABLE)
        assert build.kind == "clarify" and build.clarify_kind == "refused"
        assert persisted["status"] == "clarifying"
        assert "not an all-clear" in build.pill_text and "Try again" in build.pill_text


# ── confirm time ─────────────────────────────────────────────────────────

class _ApplyConn:
    """Two shift-lead shifts that overlap; the manager confirmed both for Dana."""

    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    async def fetchrow(self, query, shift_id, _company_id):
        return self.rows[shift_id]

    async def fetchval(self, query, *_args):
        return 0  # advisory lock / headcount COUNT

    async def fetch(self, query, *args):
        if "FOR UPDATE" in query and "FROM schedule_shifts" in query:
            return [{"id": sid} for sid in args[1]]
        return []  # roster rows / strip rows

    async def execute(self, query, *args):
        self.executed.append((query, args))


def _shift_row(shift_id, *, hour):
    return {
        "id": shift_id, "starts_at": datetime(2026, 8, 23, hour, tzinfo=UTC),
        "ends_at": datetime(2026, 8, 23, hour + 8, tzinfo=UTC), "status": "draft", "role": "shift lead",
        "location_id": None, "job_id": None, "break_minutes": 0, "kind": "work",
        "training_requirement_id": None, "published_at": None, "required_staff": 1,
    }


class TestApplyEditOpsIntraBatchCopy:
    def test_second_overlapping_assign_is_blamed_on_the_batch_not_on_drift(self):
        s1, s2 = uuid4(), uuid4()
        conn = _ApplyConn({s1: _shift_row(s1, hour=6), s2: _shift_row(s2, hour=10)})
        ops = [
            {**_op(0, shift_id=str(s1)), "to_employee_id": DANA},
            {**_op(1, shift_id=str(s2), start=(23, 10), end=(23, 18)), "to_employee_id": DANA},
        ]
        applied = []

        async def fake_find_conflicts(conn_, company_id, employee_id, starts_at, ends_at, *, exclude_shift_id=None):
            # After op 0 lands, op 1 sees it — the real query would too.
            return [{"shift_id": str(s1), "starts_at": "2026-08-23T06:00:00+00:00",
                     "ends_at": "2026-08-23T14:00:00+00:00", "role": "shift lead", "status": "draft"}] if applied else []

        async def fake_apply(conn_, company_id, *, shift_row, employee_id, actor_user_id, audit_details=None):
            applied.append(shift_row["id"])

        async def fake_qualified(conn_, *, company_id, job_id, employee_ids, as_of):
            return set(employee_ids)

        async def fake_compliance(*_a, **_k):
            return [{"check": "weekly_overtime", "severity": "advisory",
                     "message": "Employee is scheduled 48.0h this week — past 40h incurs weekly overtime; ensure overtime pay.",
                     "statute": "FLSA, 29 U.S.C. § 207(a)", "state": "TX"}]

        async def fake_availability(conn_, company_id, ids):
            return {eid: {} for eid in ids}

        audit = mock.AsyncMock()
        with (
            mock.patch.object(schedule_chat, "find_conflicts", fake_find_conflicts),
            mock.patch.object(schedule_chat, "apply_assignment_core", fake_apply),
            mock.patch.object(schedule_chat, "fetch_effective_job_employee_ids", fake_qualified),
            mock.patch.object(schedule_chat, "check_shift_compliance", fake_compliance),
            mock.patch.object(schedule_chat, "fetch_availability", fake_availability),
            mock.patch.object(schedule_chat, "lock_scheduling_employees", mock.AsyncMock()),
            mock.patch.object(schedule_chat, "log_audit", audit),
        ):
            text, touched = _run(schedule_chat._apply_edit_ops(
                conn, company_id=COMPANY, proposal_id=uuid4(), ops=ops, confirmed_by=USER,
                edit_published=True, week_start=None, week_end=None, jurisdiction=UNMAPPED,
            ))

        assert touched == [s1]
        assert "1 change is live" in text
        assert "would overlap the Shift Lead Sun Aug 23 06:00 shift applied earlier in this batch" in text
        assert "picked up a conflicting shift in the meantime" not in text
        # The acknowledged statutory advisory and the not-verified line reach the result.
        assert "Heads up on Dana Reyes: Employee is scheduled 48.0h this week" in text
        assert "(FLSA, 29 U.S.C. § 207(a))" in text
        assert "Legality was NOT verified for TX" in text and "you confirmed with that in view" in text
        # …and the audit row.
        confirm_call = next(c for c in audit.await_args_list if c.args[5] == "schedule_chat.edit_confirm")
        assert confirm_call.args[6]["compliance_status"] == "unmapped"
        assert confirm_call.args[6]["advisories_acknowledged"][0]["statute"] == "FLSA, 29 U.S.C. § 207(a)"

    def test_a_genuine_race_keeps_the_drift_copy(self):
        s1 = uuid4()
        conn = _ApplyConn({s1: _shift_row(s1, hour=6)})
        ops = [{**_op(0, shift_id=str(s1)), "to_employee_id": DANA}]

        async def fake_find_conflicts(*_a, **_k):
            return [{"shift_id": str(uuid4()), "starts_at": "2026-08-23T05:00:00+00:00",
                     "ends_at": "2026-08-23T09:00:00+00:00", "role": "opener", "status": "published"}]

        async def fake_qualified(conn_, *, company_id, job_id, employee_ids, as_of):
            return set(employee_ids)

        with (
            mock.patch.object(schedule_chat, "find_conflicts", fake_find_conflicts),
            mock.patch.object(schedule_chat, "fetch_effective_job_employee_ids", fake_qualified),
            mock.patch.object(schedule_chat, "lock_scheduling_employees", mock.AsyncMock()),
            mock.patch.object(schedule_chat, "log_audit", mock.AsyncMock()),
        ):
            text, touched = _run(schedule_chat._apply_edit_ops(
                conn, company_id=COMPANY, proposal_id=uuid4(), ops=ops, confirmed_by=USER,
                edit_published=True, week_start=None, week_end=None, jurisdiction=CURATED,
            ))
        assert touched == []
        assert "they picked up a conflicting shift in the meantime" in text
        assert "NOT verified" not in text
