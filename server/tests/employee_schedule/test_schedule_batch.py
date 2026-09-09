"""Batched schedule corrections — pure tests, no DB/Gemini.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_batch.py -q

Covers `schedule_batch` (cap + split plan), `schedule_chat.build_batch_proposal`
(both halves resolve before ONE row persists; a clarify from either half
persists nothing), `batch_proposal_text` (one review pill, every op and every
new shift, per-day result, one confirm line), and `execute_batch_proposal`
(edits before creates, one claim, one finalize, a raised error inside the
transaction skips finalize and propagates so the DB rolls everything back).
"""

import asyncio
import json
from datetime import date
from unittest import mock
from uuid import UUID, uuid4

import pytest

from app.matcha.services.scheduling import schedule_chat
from app.matcha.services.scheduling.schedule_batch import (
    MAX_BATCH_OPERATIONS, BatchItem, describe_operations, item_day, net_per_day,
    plan_batches, split_plan_message, summarize_operations,
)


def _run(coro):
    return asyncio.run(coro)


# ── schedule_batch ───────────────────────────────────────────────────────

class TestPlanBatches:
    def test_seven_days_of_eight_split_into_two_day_contiguous_batches(self):
        items = [BatchItem(day=date(2026, 8, 23 + d)) for d in range(7) for _ in range(8)]
        groups = plan_batches(items, cap=40)
        assert [g.operations for g in groups] == [40, 16]
        assert groups[0].days == [date(2026, 8, 23 + d) for d in range(5)]
        assert groups[1].days == [date(2026, 8, 28), date(2026, 8, 29)]
        assert not any(g.oversized for g in groups)

    def test_a_day_alone_over_the_cap_is_flagged_not_split(self):
        items = [BatchItem(day=date(2026, 8, 24)) for _ in range(45)] + [BatchItem(day=date(2026, 8, 25))]
        groups = plan_batches(items, cap=40)
        assert groups[0].oversized and groups[0].operations == 45
        assert groups[1].days == [date(2026, 8, 25)] and not groups[1].oversized

    def test_undated_items_ride_the_last_batch_when_they_fit(self):
        items = [BatchItem(day=date(2026, 8, 24)) for _ in range(38)] + [BatchItem(day=None), BatchItem(day=None)]
        groups = plan_batches(items, cap=40)
        assert len(groups) == 1 and groups[0].operations == 40 and groups[0].undated

    def test_undated_items_get_their_own_batch_when_they_do_not_fit(self):
        items = [BatchItem(day=date(2026, 8, 24)) for _ in range(40)] + [BatchItem(day=None)]
        groups = plan_batches(items, cap=40)
        assert len(groups) == 2 and groups[1].days == [] and groups[1].undated

    def test_named_swap_weight_counts_twice(self):
        items = [BatchItem(day=date(2026, 8, 24), operations=2) for _ in range(21)]
        groups = plan_batches(items, cap=40)
        assert groups[0].oversized and groups[0].operations == 42


class TestSplitPlanMessage:
    def test_names_cap_total_and_each_batch(self):
        items = [BatchItem(day=date(2026, 8, 23 + d)) for d in range(7) for _ in range(8)]
        message = split_plan_message(56, plan_batches(items, cap=40), cap=40)
        assert "56 schedule operations" in message
        assert "up to 40" in message
        assert "Smallest split is 2 batches" in message
        assert "(1) Sun Aug 23–Thu Aug 27, 40 operations" in message
        assert "(2) Fri Aug 28–Sat Aug 29, 16 operations" in message
        assert message.endswith("Send the first batch and I'll stage it for your confirmation.")

    def test_single_oversized_day_says_split_by_kind(self):
        items = [BatchItem(day=date(2026, 8, 24)) for _ in range(45)]
        message = split_plan_message(45, plan_batches(items, cap=40), cap=40)
        assert "Split it by kind" in message

    def test_default_cap_is_the_module_constant(self):
        assert MAX_BATCH_OPERATIONS == 40


class TestSmallHelpers:
    def test_item_day_reads_edit_and_create_dates(self):
        assert item_day({"target_date": "2026-08-24"}) == date(2026, 8, 24)
        assert item_day({"date": "2026-08-25T00:00:00"}) == date(2026, 8, 25)
        assert item_day({"date": "next friday"}) is None
        assert item_day({}) is None

    def test_summary_and_description(self):
        summary = summarize_operations(
            [{"kind": "cancel"}] * 3 + [{"kind": "reassign"}],
            [{"label": "opener"}] * 2,
        )
        assert summary == {"cancel": 3, "reassign": 1, "create": 2}
        assert describe_operations(6, summary) == "6 operations: 3 cancel, 1 reassign, 2 create"
        assert describe_operations(1, None) == "1 operation"

    def test_net_per_day(self):
        ops = [
            {"kind": "cancel", "starts_at": "2026-08-23T06:00:00+00:00"},
            {"kind": "cancel", "starts_at": "2026-08-23T10:00:00+00:00"},
            {"kind": "retime", "starts_at": "2026-08-24T10:00:00+00:00"},
        ]
        shifts = [{"starts_at": "2026-08-23T07:00:00+00:00"}]
        assert net_per_day(ops, shifts) == [
            (date(2026, 8, 23), 2, 0, 1),
            (date(2026, 8, 24), 0, 1, 0),
        ]


# ── batch_proposal_text ──────────────────────────────────────────────────

def _edit_doc():
    return {
        "kind": "edit", "ack": "", "ops": [
            {"kind": "cancel", "shift_id": "s1", "shift_role": "barista",
             "starts_at": "2026-08-23T06:00:00+00:00", "ends_at": "2026-08-23T10:00:00+00:00",
             "from_employee_name": None, "to_employee_name": None, "advisories": []},
            {"kind": "cancel", "shift_id": "s2", "shift_role": "barista",
             "starts_at": "2026-08-23T10:00:00+00:00", "ends_at": "2026-08-23T14:00:00+00:00",
             "from_employee_name": None, "to_employee_name": None,
             "advisories": [{"message": "Cancelling a published shift inside 14 days owes predictability pay",
                             "statute": "NYC Fair Workweek"}]},
        ],
    }


_CURATED = {"state": "CA", "status": "curated", "message": "Scheduling law for CA is on file (hand-curated)."}


def _create_doc():
    return {
        "surface": "editor", "week_start": "2026-08-23", "rules_unmapped": False,
        "jurisdiction": dict(_CURATED),
        "location": {"id": "l1", "name": "Downtown", "city": "SF", "state": "CA"},
        "shifts": [{
            "label": "barista", "role": "barista", "template_id": None, "job_id": None,
            "starts_at": "2026-08-23T07:00:00+00:00", "ends_at": "2026-08-23T15:00:00+00:00",
            "break_minutes": 30, "required_staff": 2, "location_id": "l1",
            "assignees": [{"employee_id": "e1", "name": "Aisha Kim", "violations": []}],
            "open_slots": 1, "intrinsic_violations": [], "excluded": [],
        }],
    }


class TestBatchProposalText:
    def test_one_pill_every_op_every_shift_per_day_result_one_confirm(self):
        text = schedule_chat.batch_proposal_text({
            "kind": "batch", "ack": "Got it.", "edit": _edit_doc(), "create": _create_doc(),
        })
        assert text.count("Reply **confirm**") == 1
        assert "Here's what I'd change" not in text            # the edit half's own lead line is gone
        assert "Here's what I'd put on" not in text            # so is the create half's
        assert "First, 2 changes to existing shifts" in text
        assert text.count(": cancel") == 2
        assert "Heads up: Cancelling a published shift inside 14 days owes predictability pay (NYC Fair Workweek)" in text
        assert "Then 1 new shift on the Downtown schedule" in text
        assert "**Barista** — Sun Aug 23, 07:00–15:00 · Aisha Kim (1 open)" in text
        assert "**After this:**" in text
        assert "Sun Aug 23: 2 cancelled, 1 new" in text
        assert "the cancellations and edits first, then the new shifts" in text

    def test_edits_only_batch_omits_the_create_section(self):
        text = schedule_chat.batch_proposal_text({"kind": "batch", "ack": "Ok.", "edit": _edit_doc(), "create": None})
        assert "Then " not in text
        assert "Sun Aug 23: 2 cancelled" in text


# ── build_batch_proposal ─────────────────────────────────────────────────

class TestBuildBatchProposal:
    def _ops(self):
        return _edit_doc()["ops"]

    def test_persists_one_row_and_hands_cancelled_ids_to_the_create_half(self):
        persisted = {}
        captured = {}

        async def fake_edits(conn, **kwargs):
            return self._ops()

        async def fake_creates(conn, **kwargs):
            captured.update(kwargs)
            return {k: v for k, v in _create_doc().items() if k != "surface"}

        async def fake_persist(conn, existing_id, **kwargs):
            persisted.update(kwargs)
            persisted["existing_id"] = existing_id
            return UUID("3f6b1c22-2000-4000-8000-000000000001")

        async def fake_jurisdiction(conn, company_id, ops, location_id):
            return dict(_CURATED)

        with (
            mock.patch.object(schedule_chat, "_resolve_edit_ops", fake_edits),
            mock.patch.object(schedule_chat, "_resolve_create_shifts", fake_creates),
            mock.patch.object(schedule_chat, "_persist_proposal", fake_persist),
            mock.patch.object(schedule_chat, "_ops_jurisdiction", fake_jurisdiction),
        ):
            build = _run(schedule_chat.build_batch_proposal(
                None, company_id=uuid4(), channel_id=None, source_message_id=None, created_by=uuid4(),
                edit_requests=[{"kind": "cancel"}, {"kind": "cancel"}],
                shift_requests=[{"label": "barista", "date": "2026-08-23"}],
                location_hint="Downtown", ack="Got it.", today=date(2026, 8, 20),
                original_content="fix the week", surface="editor",
                shift_statuses=("draft", "published"), week_start=date(2026, 8, 23),
            ))

        assert build.kind == "proposal"
        assert captured["ignore_shift_ids"] == ("s1", "s2")
        assert captured["parsed"]["location_hint"] == "Downtown"
        assert persisted["existing_id"] is None
        assert persisted["status"] == "proposed"
        doc = persisted["proposal"]
        assert doc["kind"] == "batch"
        assert doc["operation_count"] == 3
        assert [op["kind"] for op in doc["edit"]["ops"]] == ["cancel", "cancel"]
        assert doc["create"]["surface"] == "editor"
        assert len(doc["create"]["shifts"]) == 1
        # the edit fixture carries a Fair Workweek advisory → statutory advisories attached
        assert doc["compliance_status"] == "advisory"
        assert doc["review"]["kind"] == "batch"
        assert build.review["proposal_id"] == "3f6b1c22-2000-4000-8000-000000000001"
        assert "Reply **confirm**" in build.pill_text

    def test_edit_clarify_persists_nothing_and_skips_the_create_half(self):
        async def fake_edits(conn, **kwargs):
            return schedule_chat._Clarify("Which shift did you mean?", ["A", "B"])

        async def must_not_run(*a, **k):
            raise AssertionError("nothing past a clarify may run")

        with (
            mock.patch.object(schedule_chat, "_resolve_edit_ops", fake_edits),
            mock.patch.object(schedule_chat, "_resolve_create_shifts", must_not_run),
            mock.patch.object(schedule_chat, "_persist_proposal", must_not_run),
        ):
            build = _run(schedule_chat.build_batch_proposal(
                None, company_id=uuid4(), channel_id=None, source_message_id=None, created_by=uuid4(),
                edit_requests=[{"kind": "cancel"}], shift_requests=[{"label": "x"}],
                location_hint=None, ack="Ok.", today=date(2026, 8, 20), original_content="",
            ))
        assert build.kind == "clarify"
        assert build.proposal_id is None
        assert "Which shift did you mean?" in build.pill_text and "- A" in build.pill_text

    def test_create_clarify_persists_nothing(self):
        async def fake_edits(conn, **kwargs):
            return self._ops()

        async def fake_creates(conn, **kwargs):
            return schedule_chat._Clarify("What hours should the barista run?", [])

        async def must_not_run(*a, **k):
            raise AssertionError("a half-resolved batch must never persist")

        with (
            mock.patch.object(schedule_chat, "_resolve_edit_ops", fake_edits),
            mock.patch.object(schedule_chat, "_resolve_create_shifts", fake_creates),
            mock.patch.object(schedule_chat, "_persist_proposal", must_not_run),
        ):
            build = _run(schedule_chat.build_batch_proposal(
                None, company_id=uuid4(), channel_id=None, source_message_id=None, created_by=uuid4(),
                edit_requests=[{"kind": "cancel"}], shift_requests=[{"label": "barista"}],
                location_hint=None, ack="Ok.", today=date(2026, 8, 20), original_content="",
            ))
        assert build.kind == "clarify"
        assert build.proposal_id is None


# ── execute_batch_proposal ───────────────────────────────────────────────

class _Txn:
    def __init__(self, log):
        self.log = log

    async def __aenter__(self):
        self.log.append("txn:enter")
        return self

    async def __aexit__(self, exc_type, *_a):
        self.log.append(f"txn:exit:{'rollback' if exc_type else 'commit'}")
        return False


class _Conn:
    def __init__(self):
        self.log = []

    def transaction(self):
        return _Txn(self.log)


def _batch_row(with_creates=True):
    return {
        "id": UUID("3f6b1c22-2000-4000-8000-000000000001"), "company_id": uuid4(), "channel_id": None,
        "status": "proposed",
        "proposal": {
            "kind": "batch", "surface": "editor",
            "edit": {"ops": [{"kind": "cancel", "shift_id": "s1"}]},
            "create": {"shifts": [{"starts_at": "2026-08-23T07:00:00+00:00"}]} if with_creates else None,
        },
    }


class TestExecuteBatchProposal:
    def _patches(self, log, *, create_raises=None):
        s1, s2, s3 = uuid4(), uuid4(), uuid4()

        async def claim(conn, pid):
            log.append("claim")

        async def edits(conn, **kwargs):
            log.append("edits")
            return "edit text", [s1, s2]

        async def creates(conn, **kwargs):
            log.append("creates")
            if create_raises:
                raise create_raises
            return "create text", [s3, s2]

        async def mark(conn, pid, ids, by, text):
            log.append(("mark", ids, text))

        async def audit(conn, *a, **k):
            log.append(("audit", a[4]))

        return (
            mock.patch.object(schedule_chat, "_claim_proposal_execution", claim),
            mock.patch.object(schedule_chat, "_apply_edit_ops", edits),
            mock.patch.object(schedule_chat, "_apply_create_shifts", creates),
            mock.patch.object(schedule_chat, "_mark_confirmed", mark),
            mock.patch.object(schedule_chat, "log_audit", audit),
        ), (s1, s2, s3)

    def test_edits_run_before_creates_under_one_claim_and_one_finalize(self):
        conn = _Conn()
        patches, (s1, s2, s3) = self._patches(conn.log)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            text = _run(schedule_chat.execute_batch_proposal(
                conn, proposal_row=_batch_row(), confirmed_by=uuid4(), features={},
                week_start=date(2026, 8, 23), week_end=date(2026, 8, 29),
            ))
        assert text == "edit text\ncreate text"
        assert conn.log[:4] == ["txn:enter", "claim", "edits", "creates"]
        assert ("mark", [s1, s2, s3], "edit text\ncreate text") in conn.log
        assert ("audit", "schedule_chat.batch_confirm") in conn.log
        assert conn.log[-1] == "txn:exit:commit"
        assert conn.log.count("claim") == 1
        assert sum(1 for entry in conn.log if isinstance(entry, tuple) and entry[0] == "mark") == 1

    def test_a_failure_in_the_create_half_skips_finalize_and_rolls_back(self):
        conn = _Conn()
        patches, _ids = self._patches(conn.log, create_raises=RuntimeError("db hiccup"))
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            with pytest.raises(RuntimeError):
                _run(schedule_chat.execute_batch_proposal(
                    conn, proposal_row=_batch_row(), confirmed_by=uuid4(), features={},
                ))
        assert "edits" in conn.log and "creates" in conn.log
        assert not any(isinstance(entry, tuple) and entry[0] == "mark" for entry in conn.log)
        assert conn.log[-1] == "txn:exit:rollback"

    def test_create_scope_is_checked_before_the_claim(self):
        conn = _Conn()
        patches, _ids = self._patches(conn.log)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            with pytest.raises(schedule_chat.ProposalScopeError):
                _run(schedule_chat.execute_batch_proposal(
                    conn, proposal_row=_batch_row(), confirmed_by=uuid4(), features={},
                    week_start=date(2026, 8, 30), week_end=date(2026, 9, 5),
                ))
        assert conn.log == []   # nothing entered, nothing claimed, nothing cancelled

    def test_edits_only_batch_skips_the_create_half(self):
        conn = _Conn()
        patches, (s1, s2, _s3) = self._patches(conn.log)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            text = _run(schedule_chat.execute_batch_proposal(
                conn, proposal_row=_batch_row(with_creates=False), confirmed_by=uuid4(), features={},
            ))
        assert text == "edit text"
        assert "creates" not in conn.log
        assert ("mark", [s1, s2], "edit text") in conn.log


class TestCreateCandidateMode:
    def test_named_only_mode_leaves_an_unnamed_shift_open(self):
        employee_id = uuid4()
        roster = [{"id": employee_id, "first_name": "Dana", "last_name": "Reyes"}]
        shifts = [{"pinned_ids": []}]

        assert schedule_chat._create_candidate_roster(
            roster, shifts, auto_assign_unpinned=False,
        ) == []
        assert schedule_chat._create_candidate_roster(
            roster, shifts, auto_assign_unpinned=True,
        ) == roster

    def test_named_only_mode_keeps_only_explicit_employees(self):
        named, other = uuid4(), uuid4()
        roster = [{"id": named}, {"id": other}]

        assert schedule_chat._create_candidate_roster(
            roster, [{"pinned_ids": [str(named)]}], auto_assign_unpinned=False,
        ) == [{"id": named}]


class TestExecutionReceipt:
    def test_confirmation_persists_message_and_ids_atomically(self):
        proposal_id, actor_id, shift_id = uuid4(), uuid4(), uuid4()

        class Conn:
            call = None

            async def execute(self, query, *args):
                self.call = (query, args)

        conn = Conn()
        _run(schedule_chat._mark_confirmed(
            conn, proposal_id, [shift_id], actor_id, "Schedule updated.",
        ))

        query, args = conn.call
        receipt = json.loads(args[2])
        assert "jsonb_set" in query
        assert args[0] == [shift_id]
        assert args[1] == actor_id
        assert args[3] == proposal_id
        assert receipt == {
            "version": 1,
            "message": "Schedule updated.",
            "touched_shift_ids": [str(shift_id)],
        }


class TestSingleKindExecutorsStillFinalize:
    """The refactor hoisted claim/finalize out of the bodies; the public
    single-kind executors must still do both, exactly once."""

    def test_execute_edit_proposal_claims_and_marks(self):
        conn = _Conn()
        log = conn.log
        ids = [uuid4()]

        async def claim(conn, pid):
            log.append("claim")

        async def edits(conn, **kwargs):
            log.append("edits")
            return "text", ids

        async def mark(conn, pid, got, by, text):
            log.append(("mark", got, text))

        with (
            mock.patch.object(schedule_chat, "_claim_proposal_execution", claim),
            mock.patch.object(schedule_chat, "_apply_edit_ops", edits),
            mock.patch.object(schedule_chat, "_mark_confirmed", mark),
        ):
            text = _run(schedule_chat.execute_edit_proposal(
                conn,
                proposal_row={
                    "id": uuid4(), "company_id": uuid4(),
                    "proposal": {"kind": "edit", "ops": []},
                },
                confirmed_by=uuid4(),
                features={},
            ))
        assert text == "text"
        assert log == [
            "txn:enter", "claim", "edits", ("mark", ids, "text"), "txn:exit:commit",
        ]

    def test_execute_proposal_raises_scope_error_before_claiming(self):
        conn = _Conn()

        async def must_not(*a, **k):
            raise AssertionError("out-of-week create must not claim")

        with (
            mock.patch.object(schedule_chat, "_claim_proposal_execution", must_not),
            pytest.raises(
                schedule_chat.ProposalScopeError,
                match="outside the selected schedule week",
            ),
        ):
            _run(schedule_chat.execute_proposal(
                conn,
                proposal_row={
                    "id": uuid4(), "company_id": uuid4(),
                    "proposal": {"shifts": [{
                        "starts_at": "2026-08-23T07:00:00+00:00",
                    }]},
                },
                confirmed_by=uuid4(), features={},
                week_start=date(2026, 8, 30), week_end=date(2026, 9, 5),
            ))
        assert conn.log == []
