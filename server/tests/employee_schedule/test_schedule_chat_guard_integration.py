"""The assignment guard inside schedule_chat — stage-time split into staged /
not-staged, the fail-closed jurisdiction gate, and the confirm-time copy for
an overlap Huume itself created. Fakes only; no DB.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_guard_integration.py -q
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest import mock
from uuid import UUID, uuid4

import pytest

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


class _GuardConn:
    """Read-only scheduling fake; range predicates and qualification are real inputs."""
    def __init__(self, shifts, assignments=(), *, max_days=None, qualified=()):
        self.shifts = {row["id"]: row for row in shifts}
        self.assignments = list(assignments)  # (shift_id, employee_id)
        self.max_days = max_days
        self.qualified = set(qualified)

    async def fetchval(self, query, *args):
        if "schedule_job_employees" in query:
            return True  # this job has a roster, so qualification is gated
        return None

    async def fetch(self, query, *args):
        if "employee_schedule_profiles" in query:
            return [{"id": eid, "first_name": "Crew", "last_name": "Member",
                     "max_weekly_minutes": None, "max_consecutive_days": self.max_days,
                     "allow_overtime": False} for eid in args[1]]
        if "s.id AS shift_id" in query:
            return [{"employee_id": eid, "shift_id": sid, **{k: row[k] for k in
                     ("starts_at", "ends_at", "role", "break_minutes")}}
                    for sid, eid in self.assignments for row in [self.shifts[sid]]
                    if eid in args[1] and row["starts_at"] < args[3] and row["ends_at"] > args[2]]
        if "COUNT(a.employee_id)" in query:
            return [{"id": sid, "required_staff": self.shifts[sid]["required_staff"],
                     "assigned": sum(s == sid for s, _ in self.assignments)} for sid in args[1]]
        if "FROM schedule_job_employees" in query:
            return [{"employee_id": eid} for eid in args[2] if eid in self.qualified]
        raise AssertionError(query)


def _guard(conn, ops):
    with (
        mock.patch.object(schedule_chat, "resolve_week_start_weekday", mock.AsyncMock(return_value=0)),
        mock.patch.object(schedule_chat, "fetch_availability", mock.AsyncMock(return_value={})),
    ):
        _run(schedule_chat._review_assign_ops(conn, COMPANY, ops, location_id=None))


class TestGuardAdapter:
    def test_overlap_rejected_before_headroom_is_consumed(self):
        old, target, other = uuid4(), uuid4(), uuid4()
        conn = _GuardConn([_shift_row(old, hour=6), _shift_row(target, hour=10)], [(old, UUID(DANA))])
        ops = [_op(0, shift_id=str(target), start=(23, 10), end=(23, 18)),
               {**_op(1, shift_id=str(target), start=(23, 10), end=(23, 18)), "to_employee_id": str(other)}]
        _guard(conn, ops)
        assert ops[0]["review"]["verdict"] == "blocked"
        assert ops[1]["review"]["verdict"] == "ok"

    def test_cancellation_frees_the_employee_for_replacement(self):
        old, target = uuid4(), uuid4()
        conn = _GuardConn([_shift_row(old, hour=6), _shift_row(target, hour=6)], [(old, UUID(DANA))])
        ops = [{**_op(0, shift_id=str(old)), "kind": "cancel", "to_employee_id": None,
                "from_employee_id": DANA}, _op(1, shift_id=str(target))]
        _guard(conn, ops)
        assert ops[1]["review"]["verdict"] == "ok"
        assert ops[1]["review"]["before"]["minutes"] == 0

    def test_loader_counts_breaks_and_extends_context_for_profile_cap(self):
        target = _shift_row(uuid4(), hour=9)
        old = [{**target, "id": uuid4(), "starts_at": target["starts_at"] - timedelta(days=d),
                "ends_at": target["ends_at"] - timedelta(days=d), "break_minutes": 60}
               for d in range(1, 15)]
        conn = _GuardConn([target, *old], [(s["id"], UUID(DANA)) for s in old], max_days=14)
        op = _op(0, shift_id=str(target["id"]), start=(23, 9), end=(23, 17))
        _guard(conn, [op])
        assert any(r["code"] == "consecutive_days" and "15 days" in r["message"]
                   for r in op["review"]["reasons"])
        # Review an additional shift in the existing week to verify DB break deductions.
        op = _op(1, shift_id=str(target["id"]), start=(22, 18), end=(22, 22))
        _guard(conn, [op])
        assert op["review"]["before"]["minutes"] == 7 * 7 * 60

    def test_resolver_preserves_job_and_persists_only_qualified_assignments(self):
        sid, job, eligible = uuid4(), uuid4(), uuid4()
        row = {**_shift_row(sid, hour=6), "job_id": job}
        conn = _GuardConn([row], qualified=[eligible])
        persist = mock.AsyncMock(return_value=uuid4())

        async def match(_conn, _company, name, _location):
            return {"employee": {"id": UUID(DANA) if name == "Dana" else eligible,
                                 "first_name": name, "last_name": "Employee"}}

        with (
            mock.patch.object(schedule_chat, "_match_single_employee", match),
            mock.patch.object(schedule_chat, "_resolve_shift_ref", mock.AsyncMock(return_value={"shift": row})),
            mock.patch.object(schedule_chat, "check_shift_compliance", mock.AsyncMock(return_value=[])),
            mock.patch.object(schedule_chat, "resolve_week_start_weekday", mock.AsyncMock(return_value=0)),
            mock.patch.object(schedule_chat, "fetch_availability", mock.AsyncMock(return_value={})),
            mock.patch.object(schedule_chat, "_ops_jurisdiction", mock.AsyncMock(return_value=CURATED)),
            mock.patch.object(schedule_chat, "_persist_proposal", persist),
        ):
            build = _run(schedule_chat.build_edit_proposal(
                conn, company_id=COMPANY, channel_id=None, source_message_id=None,
                created_by=USER, parsed={"edit_requests": [
                    {"kind": "assign", "target_shift_id": str(sid), "to_employee_name": name}
                    for name in ("Dana", "Eligible")
                ]}, today=row["starts_at"].date(), original_content="assign two people",
            ))
        doc = persist.await_args.kwargs["proposal"]
        assert build.kind == "proposal"
        assert [op["to_employee_id"] for op in doc["ops"]] == [str(eligible)]
        assert doc["ops"][0]["job_id"] == str(job)
        assert doc["rejected"][0]["reasons"][0]["code"] == "not_qualified"


class TestCrossStoreJurisdiction:
    @pytest.mark.parametrize("second_status", ["unmapped", "unavailable"])
    def test_swap_resolves_and_checks_both_locations(self, second_status):
        first = {**_shift_row(uuid4(), hour=6), "location_id": uuid4()}
        second = {**_shift_row(uuid4(), hour=10), "location_id": uuid4()}
        status = mock.AsyncMock(side_effect=lambda _c, _co, loc: (
            {"state": "CA", "status": "curated"} if loc == first["location_id"]
            else {"state": "TX", "status": second_status}
        ))
        persist = mock.AsyncMock(return_value=uuid4())
        with (
            mock.patch.object(schedule_chat, "_resolve_shift_ref", mock.AsyncMock(side_effect=[
                {"shift": first}, {"shift": second},
            ])),
            mock.patch.object(schedule_chat, "jurisdiction_rule_status", status),
            mock.patch.object(schedule_chat, "_persist_proposal", persist),
        ):
            build = _run(schedule_chat.build_edit_proposal(
                _PersistConn(), company_id=COMPANY, channel_id=None, source_message_id=None,
                created_by=USER, parsed={"edit_requests": [{"kind": "swap", "second_role_hint": "lead"}]},
                today=first["starts_at"].date(), original_content="swap stores",
            ))
        assert [c.args[2] for c in status.await_args_list] == [first["location_id"], second["location_id"]]
        doc = persist.await_args.kwargs["proposal"]
        if second_status == "unavailable":
            assert build.kind == "clarify" and build.clarify_kind == "refused"
            assert persist.await_args.kwargs["status"] == "clarifying"
        else:
            assert build.review["compliance_status"] == "unmapped"
            assert doc["ops"][0]["second_location_id"] == str(second["location_id"])
            assert "NOT verified for TX" in build.pill_text

    def test_unlocated_operation_is_not_hidden_by_a_curated_neighbor(self):
        loc = uuid4()
        status = mock.AsyncMock(side_effect=lambda _c, _co, location: (
            {"state": "CA", "status": "curated"} if location else {"state": None, "status": "unmapped"}
        ))
        with mock.patch.object(schedule_chat, "jurisdiction_rule_status", status):
            jurisdiction = _run(schedule_chat._ops_jurisdiction(
                None, COMPANY, [{"location_id": str(loc)}, {"location_id": None}], None,
            ))
        assert jurisdiction["status"] == "unmapped"


def _resolved_create(jurisdiction):
    return {"week_start": "2026-08-23", "location": {"id": str(uuid4()), "name": "Store", "state": "TX"},
            "rules_unmapped": True, "jurisdiction": jurisdiction, "shifts": [{
                "label": "lead", "starts_at": "2026-08-23T06:00:00+00:00",
                "ends_at": "2026-08-23T14:00:00+00:00", "assignees": [], "open_slots": 1,
                "intrinsic_violations": [], "excluded": [],
            }]}


class TestCreateJurisdictionGate:
    def test_create_builders_forward_named_only_mode(self):
        persist = mock.AsyncMock(return_value=uuid4())
        standalone_resolver = mock.AsyncMock(return_value=_resolved_create(CURATED))
        with (
            mock.patch.object(schedule_chat, "_resolve_create_shifts", standalone_resolver),
            mock.patch.object(schedule_chat, "_persist_proposal", persist),
        ):
            _run(schedule_chat.build_proposal(
                _PersistConn(), company_id=COMPANY, channel_id=None,
                source_message_id=None, created_by=USER, parsed={"ack": "OK"},
                today=date(2026, 8, 20), original_content="create",
                auto_assign_unpinned=False,
            ))
        assert standalone_resolver.await_args.kwargs["auto_assign_unpinned"] is False

        batch_resolver = mock.AsyncMock(return_value=_resolved_create(CURATED))
        with (
            mock.patch.object(schedule_chat, "_resolve_create_shifts", batch_resolver),
            mock.patch.object(schedule_chat, "_persist_proposal", persist),
        ):
            _run(schedule_chat.build_batch_proposal(
                _PersistConn(), company_id=COMPANY, channel_id=None,
                source_message_id=None, created_by=USER, edit_requests=[],
                shift_requests=[{}], location_hint=None, ack="OK",
                today=date(2026, 8, 20), original_content="create",
                auto_assign_unpinned=False,
            ))
        assert batch_resolver.await_args.kwargs["auto_assign_unpinned"] is False

    @pytest.mark.parametrize("jurisdiction", [UNAVAILABLE, UNMAPPED])
    def test_standalone_create_refuses_unavailable_but_stages_unmapped(self, jurisdiction):
        persist = mock.AsyncMock(return_value=uuid4())
        with (
            mock.patch.object(schedule_chat, "_resolve_create_shifts", mock.AsyncMock(return_value=_resolved_create(jurisdiction))),
            mock.patch.object(schedule_chat, "_persist_proposal", persist),
        ):
            build = _run(schedule_chat.build_proposal(
                _PersistConn(), company_id=COMPANY, channel_id=None, source_message_id=None,
                created_by=USER, parsed={"ack": "OK"}, today=datetime(2026, 8, 20).date(), original_content="create",
            ))
        kwargs = persist.await_args.kwargs
        if jurisdiction["status"] == "unavailable":
            assert build.kind == "clarify" and build.clarify_kind == "refused"
            assert kwargs["status"] == "clarifying" and not kwargs["proposal"].get("shifts")
            assert "Try again" in build.pill_text
        else:
            assert build.kind == "proposal" and kwargs["status"] == "proposed"
            assert build.review["compliance_status"] == "unmapped"

    @pytest.mark.parametrize("all_blocked", [True, False])
    @pytest.mark.parametrize("with_create", [True, False])
    def test_batch_persists_only_accepted_ops_and_counts_creates(self, all_blocked, with_create):
        rejected = _op(0, verdict="blocked", reasons=[{
            "code": "existing_overlap", "policy": False, "message": "already on another shift",
        }])
        ops = [rejected] if all_blocked else [rejected, _op(1)]
        persist = mock.AsyncMock(return_value=uuid4())
        with (
            mock.patch.object(schedule_chat, "_resolve_edit_ops", mock.AsyncMock(return_value=ops)),
            mock.patch.object(schedule_chat, "_resolve_create_shifts", mock.AsyncMock(return_value=_resolved_create(CURATED))),
            mock.patch.object(schedule_chat, "_ops_jurisdiction", mock.AsyncMock(return_value=CURATED)),
            mock.patch.object(schedule_chat, "_persist_proposal", persist),
        ):
            build = _run(schedule_chat.build_batch_proposal(
                None, company_id=COMPANY, channel_id=None, source_message_id=None, created_by=USER,
                edit_requests=[{}], shift_requests=[{}] if with_create else [], location_hint=None,
                ack="OK", today=datetime(2026, 8, 20).date(), original_content="correct the week",
            ))
        if all_blocked and not with_create:
            assert build.kind == "clarify" and build.clarify_kind == "refused"
            persist.assert_not_awaited()
            return
        doc = persist.await_args.kwargs["proposal"]
        assert [op["shift_id"] for op in (doc.get("edit") or {}).get("ops", [])] == ([] if all_blocked else ["s1"])
        assert doc["rejected"][0]["shift_id"] == "s0"
        assert doc["rejected"][0]["reasons"][0]["code"] == "existing_overlap"
        assert build.review["operation_count"] == int(not all_blocked) + int(with_create)


class TestConfirmRetimeAttribution:
    def test_earlier_retime_is_named_as_the_source_of_the_overlap(self):
        first, second = uuid4(), uuid4()
        rows = {first: _shift_row(first, hour=6), second: _shift_row(second, hour=12)}
        rows[first]["ends_at"] = rows[first]["ends_at"].replace(hour=10)
        rows[second]["ends_at"] = rows[second]["ends_at"].replace(hour=16)

        class Conn(_ApplyConn):
            async def fetch(self, query, *args):
                if "SELECT employee_id FROM schedule_shift_assignments" in query:
                    return [{"employee_id": UUID(DANA)}]
                return await super().fetch(query, *args)

        async def conflicts(_conn, _company, _employee, start, end, *, exclude_shift_id=None):
            row = rows[first]
            if exclude_shift_id != first and row["starts_at"] < end and row["ends_at"] > start:
                return [{"shift_id": str(first), "starts_at": row["starts_at"].isoformat(),
                         "ends_at": row["ends_at"].isoformat(), "role": "shift lead"}]
            return []

        async def retime(_conn, _company, **kwargs):
            rows[kwargs["shift_id"]].update(starts_at=kwargs["new_starts_at"], ends_at=kwargs["new_ends_at"])

        ops = [{**_op(0, shift_id=str(first)), "kind": "retime", "to_employee_id": None,
                "new_starts_at": "2026-08-23T10:00:00+00:00", "new_ends_at": "2026-08-23T14:00:00+00:00"},
               _op(1, shift_id=str(second), start=(23, 12), end=(23, 16))]
        with (
            mock.patch.object(schedule_chat, "find_conflicts", conflicts),
            mock.patch.object(schedule_chat, "retime_shift_core", retime),
            mock.patch.object(schedule_chat, "fetch_effective_job_employee_ids", mock.AsyncMock(return_value={UUID(DANA)})),
            mock.patch.object(schedule_chat, "check_shift_compliance", mock.AsyncMock(return_value=[])),
            mock.patch.object(schedule_chat, "lock_scheduling_employees", mock.AsyncMock()),
            mock.patch.object(schedule_chat, "log_audit", mock.AsyncMock()),
        ):
            text, touched = _run(schedule_chat._apply_edit_ops(
                Conn(rows), company_id=COMPANY, proposal_id=uuid4(), ops=ops, confirmed_by=USER,
                edit_published=True, week_start=None, week_end=None,
            ))
        assert touched == [first]
        assert "shift applied earlier in this batch" in text
        assert "picked up a conflicting shift in the meantime" not in text
