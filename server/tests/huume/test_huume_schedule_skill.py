"""Pure-function tests for the schedule-change staged action + the
find_shift_coverage read tool's gates (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_schedule_skill.py -q

Covers `evaluate_huume_action`'s `schedule_change` branch, the
`propose_schedule_change` registry entry in `_HR_OPS_TOOL_SPECS` (mirrors
`test_huume_inventory.py`'s shape), and `schedule_skill.find_coverage`'s
role/feature gate — proven without a database the same way
`channel_grounding`'s gate tests are (asserting the refusal never reaches
a DB call).
"""

import asyncio
import unittest
from datetime import date as _date
from unittest import mock
from uuid import uuid4

from app.matcha.services.huume.actions import evaluate_huume_action
from app.matcha.services.huume.agent import _HR_OPS_TOOL_SPECS, _build_hr_ops_staged
from app.matcha.services.huume.tools import TOOLS_BY_NAME
from app.matcha.services.huume import schedule_skill
from app.matcha.services.scheduling import schedule_chat
from app.matcha.services.scheduling.schedule_batch import MAX_BATCH_OPERATIONS, item_day

BASE_ON = {"huume": True, "matcha_work": True, "employee_schedule": True}
PROPOSAL_ID = "3f6b1c22-2000-4000-8000-000000000001"


def _run(coro):
    return asyncio.run(coro)


def _features(**extra):
    return {**BASE_ON, **extra}


def _change(**overrides):
    base = {"type": "schedule_change", "status": "proposed", "confirm_id": "cc33dd44",
            "kind": "reassign", "proposal_id": PROPOSAL_ID}
    base.update(overrides)
    return base


class TestRegistry:
    def test_tool_declared(self):
        assert "propose_schedule_change" in TOOLS_BY_NAME
        assert TOOLS_BY_NAME["propose_schedule_change"].kind == "staged"

    def test_coverage_tool_is_read(self):
        assert TOOLS_BY_NAME["find_shift_coverage"].kind == "read"

    def test_schema_declares_target_time_hint(self):
        # Without this, the model has no field to disambiguate "assign
        # Elena to one of them" when several shifts share a date — a real
        # transcript hit exactly that and staging refused outright.
        tool = TOOLS_BY_NAME["propose_schedule_change"]
        assert "target_time_hint" in tool.declaration.parameters.properties

    def test_schema_declares_second_time_hint(self):
        tool = TOOLS_BY_NAME["propose_schedule_change"]
        assert "second_time_hint" in tool.declaration.parameters.properties

    def test_intent_hints_are_multiword_only(self):
        # A bare "assign" substring-matched training/PTO assignment asks
        # that have nothing to do with scheduling — every hint here must be
        # multi-word so it can't collide with an unrelated skill's phrasing.
        hints = TOOLS_BY_NAME["propose_schedule_change"].intent_hints
        assert "assign" not in hints
        assert any("assign" in h for h in hints)
        assert all(" " in h for h in hints)

    def test_spec_fields_forward_target_time_hint(self):
        assert "target_time_hint" in _HR_OPS_TOOL_SPECS["propose_schedule_change"]["fields"]

    def test_spec_fields_forward_second_time_hint(self):
        assert "second_time_hint" in _HR_OPS_TOOL_SPECS["propose_schedule_change"]["fields"]

    def test_schema_declares_target_staffing_hint(self):
        # Two shifts can share the exact date AND time AND role (one
        # staffed, one open) — target_time_hint alone can't separate them.
        tool = TOOLS_BY_NAME["propose_schedule_change"]
        props = tool.declaration.parameters.properties
        assert "target_staffing_hint" in props
        assert set(props["target_staffing_hint"].enum) == {"staffed", "unstaffed"}

    def test_schema_declares_bounded_batch_with_creates(self):
        """The batch cap in the tool schema IS the domain constant — the
        prompt, the schema and the refusal copy can never disagree — and a
        replacement shift (`kind: create`) rides the same array as the
        cancellations that make room for it."""
        tool = TOOLS_BY_NAME["propose_schedule_change"]
        changes = tool.declaration.parameters.properties["changes"]
        assert changes.min_items == 1
        assert changes.max_items == MAX_BATCH_OPERATIONS
        assert MAX_BATCH_OPERATIONS > 4
        assert changes.items.required == ["kind"]
        assert "create" in changes.items.properties["kind"].enum
        for create_field in ("label", "date", "start_time", "end_time", "count", "employee_names"):
            assert create_field in changes.items.properties
        # The flat legacy fields keep their edit-only enum: a top-level
        # create still goes through build_proposal unchanged.
        assert "create" in tool.declaration.parameters.properties["kind"].enum

    def test_confirm_call_does_not_require_irrelevant_kind(self):
        tool = TOOLS_BY_NAME["propose_schedule_change"]
        assert "kind" not in (tool.declaration.parameters.required or [])

    def test_spec_fields_forward_target_staffing_hint(self):
        assert "target_staffing_hint" in _HR_OPS_TOOL_SPECS["propose_schedule_change"]["fields"]

    def test_spec_fields_forward_changes_batch(self):
        assert "changes" in _HR_OPS_TOOL_SPECS["propose_schedule_change"]["fields"]

    def test_spec_mints_a_confirm_id(self):
        spec = _HR_OPS_TOOL_SPECS["propose_schedule_change"]
        staged, confirming = _build_hr_ops_staged(spec, {"kind": "cancel"}, None)
        assert confirming is False
        assert staged["confirm_id"] and len(staged["confirm_id"]) == 8
        assert staged["type"] == "schedule_change"

    def test_confirm_turn_matches_on_confirm_id(self):
        spec = _HR_OPS_TOOL_SPECS["propose_schedule_change"]
        pre_turn, _ = _build_hr_ops_staged(spec, {"kind": "cancel"}, None)
        staged, confirming = _build_hr_ops_staged(
            spec, {"kind": "cancel", "confirm_id": pre_turn["confirm_id"]}, pre_turn)
        assert confirming is True
        assert staged is pre_turn


class TestEvaluateHuumeAction:
    def test_stage_turn_needs_no_feature_yet_to_report_stage(self):
        verdict = evaluate_huume_action(
            staged_action=_change(status="proposed"), features=_features(),
            role="client", thread_huume_mode=True, this_turn_staged_new=True,
        )
        assert verdict.kind == "stage"

    def test_confirm_refused_when_feature_off(self):
        verdict = evaluate_huume_action(
            staged_action=_change(), features=_features(employee_schedule=False),
            role="client", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert not verdict.ok

    def test_confirm_refused_for_wrong_role(self):
        verdict = evaluate_huume_action(
            staged_action=_change(), features=_features(),
            role="employee", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert not verdict.ok

    def test_confirm_proceeds_with_admin_and_feature_on(self):
        verdict = evaluate_huume_action(
            staged_action=_change(), features=_features(),
            role="admin", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert verdict.ok

    def test_already_applied_is_idempotent_refusal(self):
        verdict = evaluate_huume_action(
            staged_action=_change(status="applied"), features=_features(),
            role="admin", thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert not verdict.ok


class TestFindCoverageGates:
    def test_non_admin_refused_without_touching_conn(self):
        # No DB call in scope here — a real one would raise, since this test
        # never opens a connection. Reaching one fails the test as a side
        # effect the same way channel_grounding's gate tests prove it.
        result = _run(schedule_skill.find_coverage(
            company_id="c1", role="employee", features=_features(),
            date_str="2026-08-05", role_hint=None,
        ))
        assert "error" in result
        assert "admin" in result["error"].lower()

    def test_feature_off_refused(self):
        result = _run(schedule_skill.find_coverage(
            company_id="c1", role="admin", features=_features(employee_schedule=False),
            date_str="2026-08-05", role_hint=None,
        ))
        assert "error" in result
        assert "enabled" in result["error"].lower()

    def test_bad_date_refused(self):
        result = _run(schedule_skill.find_coverage(
            company_id="c1", role="admin", features=_features(),
            date_str="not-a-date", role_hint=None,
        ))
        assert "error" in result
        assert "date" in result["error"].lower()


class TestExecuteNoProposal:
    def test_missing_proposal_id_errors_without_a_db_call(self):
        result = _run(schedule_skill.execute(
            company_id="c1", actor_user_id="u1", action=_change(proposal_id=None),
        ))
        assert result["status"] == "error"


class TestProposeClarify(unittest.TestCase):
    """A build_edit_proposal 'clarify' result (ambiguous shift, e.g. several
    shifts share the target date) has no thread-side round-trip — propose()
    surfaces it as a terminal clarification instead of staging an
    unconfirmable proposal.
    Previously that refusal kept only the question's first line, dropping
    the numbered candidate list the model needs to relay back to the admin
    — the real failure behind "Assign Elena to one of them" going nowhere."""

    def test_clarify_keeps_full_option_list_and_hints_target_time_hint(self):
        pill = schedule_chat.clarify_text(
            "Which shift did you mean?",
            ["Shift — Fri Aug 7 08:00–16:00 · Aisha Kim", "Shift — Fri Aug 7 12:30–18:00 · unstaffed"],
        )
        build = schedule_chat.ProposalBuild(
            kind="clarify", proposal_id="3f6b1c22-2000-4000-8000-000000000099", pill_text=pill,
        )

        async def fake_build_edit_proposal(*args, **kwargs):
            return build

        with mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"kind": "assign", "to_employee_name": "Elena", "target_date": "2026-08-07"},
            ))

        assert result["status"] == "clarify"
        assert "Aisha Kim" in result["message"]  # first option survived
        assert "unstaffed" in result["message"]  # second option survived
        assert "shift time" in result["message"]
        assert "employee" in result["message"]
        assert "staffed or unstaffed" in result["message"]
        # Channel-only UX ("reply to the pill") has no meaning in a thread,
        # and directly contradicts terminal handling in the agent loop.
        assert "Just reply to this message" not in result["message"]
        assert "Ask the admin" not in result["message"]

    def test_success_returns_ready_result(self):
        build = schedule_chat.ProposalBuild(
            kind="edit", proposal_id=PROPOSAL_ID, pill_text="Schedule change pill",
        )

        async def fake_build_edit_proposal(*args, **kwargs):
            return build

        with mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"kind": "assign", "to_employee_name": "Elena", "target_date": "2026-08-07"},
            ))

        assert result == {
            "status": "ready", "proposal_id": PROPOSAL_ID, "pill_text": "Schedule change pill",
            "operation_count": 1, "operation_summary": {"assign": 1},
            # A build with no review (fake) reports fail-closed: nothing verified.
            "review": {}, "rejected_count": 0, "unfilled_count": 0, "compliance_status": "unmapped",
        }

    def test_changes_batch_reaches_existing_multi_op_builder(self):
        build = schedule_chat.ProposalBuild(
            kind="edit", proposal_id=PROPOSAL_ID, pill_text="Two-change schedule pill",
        )
        captured = {}

        async def fake_build_edit_proposal(*args, **kwargs):
            captured.update(kwargs["parsed"])
            return build

        with mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"changes": [
                    {
                        "kind": "assign", "to_employee_name": "Bea Haddad",
                        "target_date": "2026-08-27", "target_time_hint": "17:00",
                        "target_staffing_hint": "unstaffed",
                    },
                    {
                        "kind": "retime", "target_employee_name": "Elena Iyer",
                        "target_date": "2026-08-28", "target_time_hint": "08:00",
                        "shift_by_minutes": 30,
                    },
                ]},
            ))

        assert result["status"] == "ready"
        assert result["operation_count"] == 2
        assert [request["kind"] for request in captured["edit_requests"]] == ["assign", "retime"]
        assert captured["edit_requests"][0]["target_staffing_hint"] == "unstaffed"

    def test_empty_changes_schema_default_falls_back_to_valid_flat_edit(self):
        """Gemini's structured output emits optional arrays as ``[]``. Keep
        accepting the populated legacy fields alongside that schema default."""
        build = schedule_chat.ProposalBuild(
            kind="edit", proposal_id=PROPOSAL_ID, pill_text="Schedule change pill",
        )
        captured = {}

        async def fake_build_edit_proposal(*args, **kwargs):
            captured.update(kwargs["parsed"])
            return build

        with mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={
                    "changes": [], "kind": "assign",
                    "to_employee_name": "Bea Haddad",
                    "target_employee_name": "Bea Haddad",
                    "target_date": "2026-08-24", "target_time_hint": "9:00am",
                    "target_staffing_hint": "unstaffed",
                },
            ))

        assert result["status"] == "ready"
        assert result["operation_count"] == 1
        assert captured["edit_requests"][0]["kind"] == "assign"
        assert captured["edit_requests"][0]["to_employee_name"] == "Bea Haddad"

    def test_empty_changes_schema_default_falls_back_to_flat_create(self):
        build = schedule_chat.ProposalBuild(
            kind="create", proposal_id=PROPOSAL_ID, pill_text="Create shift pill",
        )
        captured = {}
        modes = []

        async def fake_build_proposal(*args, **kwargs):
            captured.update(kwargs["parsed"])
            modes.append(kwargs["auto_assign_unpinned"])
            return build

        with mock.patch.object(schedule_chat, "build_proposal", fake_build_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={
                    "changes": [], "kind": "create", "label": "closer",
                    "target_date": "2026-08-27", "start_time": "12:00",
                    "end_time": "18:00", "count": 1,
                },
            ))

        assert result["status"] == "ready"
        assert result["operation_count"] == 1
        assert captured["shift_requests"][0]["date"] == "2026-08-27"
        assert modes == [False]

    def test_editor_resolution_includes_visible_draft_shifts(self):
        """The schedule editor deliberately exposes draft shifts. Huume must
        resolve the same rows it just showed the manager; published-only
        lookup made an explicit assignment to an open draft shift impossible
        in the live editor."""
        build = schedule_chat.ProposalBuild(
            kind="edit", proposal_id=PROPOSAL_ID, pill_text="Schedule change pill",
        )
        captured = {}

        class Conn:
            async def fetchval(self, *args):
                return "Wilshire"

        async def fake_build_edit_proposal(*args, **kwargs):
            captured.update(kwargs)
            return build

        with mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal):
            result = _run(schedule_skill.propose(
                conn=Conn(), company_id="c1", actor_user_id="u1", location_id="location-1",
                args={
                    "kind": "assign", "to_employee_name": "Bea Haddad",
                    "target_date": "2026-08-24", "target_time_hint": "09:00",
                    "target_staffing_hint": "unstaffed",
                },
            ))

        assert result["status"] == "ready"
        assert captured["surface"] == "editor"
        assert captured["shift_statuses"] == ("draft", "published")

    def test_batch_over_cap_is_refused_with_a_split_plan_before_any_builder(self):
        """Over the cap the server answers with the smallest day-contiguous
        split, never a silently staged prefix: 7 days × 8 ops = 56 > 40 →
        two batches, and NOTHING is resolved or persisted."""
        async def should_not_build(*args, **kwargs):
            raise AssertionError("oversized batch must not persist a proposal")

        changes = [
            {"kind": "cancel", "target_date": f"2026-08-{day:02d}", "target_time_hint": f"{hour:02d}:00"}
            for day in range(23, 30) for hour in range(8, 16)
        ]
        assert len(changes) == 56
        with (
            mock.patch.object(schedule_chat, "build_edit_proposal", should_not_build),
            mock.patch.object(schedule_chat, "build_batch_proposal", should_not_build),
        ):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1", args={"changes": changes},
            ))

        assert result["status"] == "clarify"
        assert f"up to {MAX_BATCH_OPERATIONS}" in result["message"]
        assert "56 schedule operations" in result["message"]
        assert "2 batches" in result["message"]
        assert "(1) Sun Aug 23–Thu Aug 27, 40 operations" in result["message"]
        assert "(2) Fri Aug 28–Sat Aug 29, 16 operations" in result["message"]

    def test_named_swap_weighs_two_toward_the_cap(self):
        async def should_not_build(*args, **kwargs):
            raise AssertionError("oversized batch must not persist a proposal")

        # 20 named-person swaps = 40 operations (at cap) + one cancel = 41.
        changes = [
            {"kind": "swap", "target_employee_name": "A", "second_employee_name": "B",
             "target_date": "2026-08-24", "target_time_hint": f"{8 + i % 8:02d}:00"}
            for i in range(20)
        ] + [{"kind": "cancel", "target_date": "2026-08-25"}]
        with (
            mock.patch.object(schedule_chat, "build_edit_proposal", should_not_build),
            mock.patch.object(schedule_chat, "build_batch_proposal", should_not_build),
        ):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1", args={"changes": changes},
            ))
        assert result["status"] == "clarify"
        assert "41 schedule operations" in result["message"]

    def test_named_people_swap_becomes_two_individual_reassignments(self):
        build = schedule_chat.ProposalBuild(
            kind="edit", proposal_id=PROPOSAL_ID, pill_text="Schedule change pill",
        )
        captured = {}

        async def fake_build_edit_proposal(*args, **kwargs):
            captured.update(kwargs["parsed"])
            return build

        with mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={
                    "kind": "swap",
                    "target_employee_name": "Aisha Kim",
                    "second_employee_name": "Elena Iyer",
                    "target_date": "2026-08-20",
                    "target_time_hint": "08:00",
                    "second_time_hint": "09:00",
                },
            ))

        assert result["status"] == "ready"
        assert captured["edit_requests"] == [
            {
                "kind": "reassign", "target_employee_name": "Aisha Kim",
                "target_date": "2026-08-20", "target_day_hint": None,
                "target_time_hint": "08:00", "target_role_hint": None,
                "target_staffing_hint": None, "to_employee_name": "Elena Iyer",
                "second_employee_name": None, "second_date": None,
                "second_day_hint": None, "second_time_hint": None,
                "second_role_hint": None, "new_date": None, "new_day_hint": None,
                "new_start_time": None, "new_end_time": None, "shift_by_minutes": None,
            },
            {
                "kind": "reassign", "target_employee_name": "Elena Iyer",
                "target_date": "2026-08-20", "target_day_hint": None,
                "target_time_hint": "09:00", "target_role_hint": None,
                "target_staffing_hint": None, "to_employee_name": "Aisha Kim",
                "second_employee_name": None, "second_date": None,
                "second_day_hint": None, "second_time_hint": None,
                "second_role_hint": None, "new_date": None, "new_day_hint": None,
                "new_start_time": None, "new_end_time": None, "shift_by_minutes": None,
            },
        ]

    def test_builder_exception_returns_refused_result(self):
        async def failing_build_edit_proposal(*args, **kwargs):
            raise RuntimeError("database unavailable")

        with mock.patch.object(schedule_chat, "build_edit_proposal", failing_build_edit_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"kind": "assign", "to_employee_name": "Elena", "target_date": "2026-08-07"},
            ))

        assert result["status"] == "refused"
        assert "Schedule page" in result["message"]


def _seven_day_correction_changes() -> list[dict]:
    """The reported interaction: four drafts a day for a week were wrong; scrap
    them and put the corrected one-shift-a-day pattern in. 28 cancels + 7
    creates = 35 operations, one confirmation."""
    cancels = [
        {"kind": "cancel", "target_date": f"2026-08-{day:02d}", "target_time_hint": f"{hour:02d}:00",
         "target_role_hint": "barista"}
        for day in range(23, 30) for hour in (6, 10, 14, 18)
    ]
    creates = [
        {"kind": "create", "label": "barista", "date": f"2026-08-{day:02d}",
         "start_time": "07:00", "end_time": "15:00", "count": 2}
        for day in range(23, 30)
    ]
    return cancels + creates


class TestSevenDayCorrectionBatch(unittest.TestCase):
    """A clarified multi-day correction is ONE staged batch: cancellations and
    replacement creates resolve through `build_batch_proposal` together —
    neither single-kind builder is touched — and the staged dict carries the
    per-kind summary the state block renders."""

    def test_cancels_and_replacements_stage_as_one_batch(self):
        build = schedule_chat.ProposalBuild(
            kind="proposal", proposal_id=PROPOSAL_ID, pill_text="Batch pill",
        )
        captured = {}

        async def fake_build_batch_proposal(conn, **kwargs):
            captured.update(kwargs)
            return build

        async def should_not_build(*args, **kwargs):
            raise AssertionError("a correction must not split across single-kind builders")

        with (
            mock.patch.object(schedule_chat, "build_batch_proposal", fake_build_batch_proposal),
            mock.patch.object(schedule_chat, "build_edit_proposal", should_not_build),
            mock.patch.object(schedule_chat, "build_proposal", should_not_build),
        ):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"changes": _seven_day_correction_changes(), "location_name": "Downtown"},
            ))

        assert result["status"] == "ready"
        assert result["proposal_id"] == PROPOSAL_ID
        assert result["operation_count"] == 35
        assert result["operation_summary"] == {"cancel": 28, "create": 7}
        assert len(captured["edit_requests"]) == 28
        assert {r["kind"] for r in captured["edit_requests"]} == {"cancel"}
        assert len(captured["shift_requests"]) == 7
        assert captured["shift_requests"][0]["date"] == "2026-08-23"
        assert captured["shift_requests"][0]["start_time"] == "07:00"
        assert captured["shift_requests"][0]["count"] == 2
        assert captured["location_hint"] == "Downtown"
        assert captured["shift_statuses"] == ("published",)  # thread surface, no editor scope
        assert captured["auto_assign_unpinned"] is False

    def test_editor_scope_reaches_the_batch_builder(self):
        from datetime import date
        from uuid import UUID as _UUID
        build = schedule_chat.ProposalBuild(kind="proposal", proposal_id=PROPOSAL_ID, pill_text="Batch pill")
        captured = {}

        async def fake_build_batch_proposal(conn, **kwargs):
            captured.update(kwargs)
            return build

        class _Conn:
            async def fetchval(self, *_a, **_k):
                return "Downtown"

        location_id = _UUID("c0ffeeee-0001-4001-8001-000000000001")
        with mock.patch.object(schedule_chat, "build_batch_proposal", fake_build_batch_proposal):
            result = _run(schedule_skill.propose(
                conn=_Conn(), company_id="c1", actor_user_id="u1",
                args={"changes": _seven_day_correction_changes()},
                location_id=location_id, week_start=date(2026, 8, 23), week_end=date(2026, 8, 29),
            ))
        assert result["status"] == "ready"
        assert captured["shift_statuses"] == ("draft", "published")
        assert captured["editor_location_id"] == location_id
        assert captured["week_start"] == date(2026, 8, 23)
        assert captured["location_hint"] == "Downtown"

    def test_batch_clarify_is_terminal_and_names_the_gap(self):
        pill = schedule_chat.clarify_text("Which shift did you mean?", ["Barista — Sun Aug 23 06:00–10:00 · Aisha Kim"])
        build = schedule_chat.ProposalBuild(kind="clarify", proposal_id=None, pill_text=pill)

        async def fake_build_batch_proposal(conn, **kwargs):
            return build

        with mock.patch.object(schedule_chat, "build_batch_proposal", fake_build_batch_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"changes": _seven_day_correction_changes()},
            ))
        assert result["status"] == "clarify"
        assert "Aisha Kim" in result["message"]
        assert "Just reply to this message" not in result["message"]

    def test_create_item_missing_hours_rejects_the_whole_batch(self):
        async def should_not_build(*args, **kwargs):
            raise AssertionError("an unusable item must reject the batch before resolution")

        changes = [
            {"kind": "cancel", "target_date": "2026-08-23", "target_time_hint": "06:00"},
            {"kind": "create", "label": "barista", "date": "2026-08-23"},
        ]
        with mock.patch.object(schedule_chat, "build_batch_proposal", should_not_build):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1", args={"changes": changes},
            ))
        assert result["status"] == "clarify"
        assert "Schedule change 2" in result["message"]
        assert "start time" in result["message"]

    def test_single_flat_edit_still_uses_the_single_kind_builder(self):
        """The existing one-edit path is untouched: no batch row for a plain
        reassign."""
        build = schedule_chat.ProposalBuild(kind="proposal", proposal_id=PROPOSAL_ID, pill_text="pill")

        async def fake_build_edit_proposal(*args, **kwargs):
            return build

        async def should_not_batch(*args, **kwargs):
            raise AssertionError("a single edit must not become a batch row")

        with (
            mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal),
            mock.patch.object(schedule_chat, "build_batch_proposal", should_not_batch),
        ):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"kind": "reassign", "target_employee_name": "Aisha Kim",
                      "to_employee_name": "Elena Iyer", "target_date": "2026-08-24"},
            ))
        assert result["status"] == "ready"
        assert result["operation_count"] == 1
        assert result["operation_summary"] == {"reassign": 1}


class _FakeScheduleChat:
    """Just enough of `schedule_chat` for the pure coercion tests: every edit
    resolves, so what's asserted is the coercion itself."""

    @staticmethod
    def coerce_edit_request(request):
        return dict(request)


class TestRequestedTimesSurviveCoercion(unittest.TestCase):
    """Reported 2026-09-10: "lets add a shift from 2pm to 830pm on sunday" →
    Barista created 06:30-14:30, and "yes, correct it" produced the same shift
    again. The hours were lost in `_resolve_create_shifts`, which matched the
    location's "Opening Barista" template on the ROLE stem and took its times
    (fixed by `template_for_request`). These two guard the leg before that: the
    hours the manager stated must still be on the request when it gets there,
    on the first ask AND on the correction."""

    SUNDAY = "2026-09-13"

    def test_the_initial_create_carries_the_requested_window(self):
        edits, shifts, error = schedule_skill._coerce_tool_batch(
            _FakeScheduleChat(),
            {"kind": "create", "label": "Barista", "role": "Barista",
             "date": self.SUNDAY, "start_time": "14:00", "end_time": "20:30"},
        )
        self.assertIsNone(error)
        self.assertEqual(edits, [])
        self.assertEqual(len(shifts), 1)
        self.assertEqual(
            (shifts[0]["date"], shifts[0]["start_time"], shifts[0]["end_time"]),
            (self.SUNDAY, "14:00", "20:30"),
        )

    def test_the_correction_cancels_the_wrong_shift_and_recreates_the_window(self):
        # What "yes, correct it" sends: cancel the 06:30-14:30 shift that was
        # created, and create the one that was asked for. Both ride one
        # confirmation, and the create still carries 14:00-20:30.
        edits, shifts, error = schedule_skill._coerce_tool_batch(
            _FakeScheduleChat(),
            {"kind": "create", "changes": [
                {"kind": "cancel", "target_shift_id": "1c6d234e-c1a0-43bc-af08-1cd08e458c78"},
                {"kind": "create", "label": "Barista", "role": "Barista",
                 "date": self.SUNDAY, "start_time": "14:00", "end_time": "20:30"},
            ]},
        )
        self.assertIsNone(error)
        self.assertEqual([e["kind"] for e in edits], ["cancel"])
        self.assertEqual(len(shifts), 1)
        self.assertEqual(
            (shifts[0]["start_time"], shifts[0]["end_time"]), ("14:00", "20:30"),
        )

    def test_the_correction_does_not_stage_the_shift_twice(self):
        # The flat copy of the same shift alongside the batch is absorbed, not
        # appended — one confirmation must not produce two 14:00-20:30 shifts.
        _, shifts, error = schedule_skill._coerce_tool_batch(
            _FakeScheduleChat(),
            {"kind": "create", "label": "Barista", "role": "Barista",
             "date": self.SUNDAY, "start_time": "14:00", "end_time": "20:30",
             "changes": [
                 {"kind": "create", "label": "Barista", "role": "Barista",
                  "date": self.SUNDAY, "start_time": "14:00", "end_time": "20:30"},
             ]},
        )
        self.assertIsNone(error)
        self.assertEqual(len(shifts), 1)


class TestFlatCreateKindAlongsideABatch(unittest.TestCase):
    """The reported full-shift-editor dead end: the model sent a `changes`
    batch AND the legacy flat `kind='create'`, and the coercion refused with
    "Put the new shift inside `changes` as a `kind: create` item…" — text
    written for the model, relayed to the manager verbatim (a schedule
    clarify/refusal is terminal for the turn), telling it to do what it had
    already done. A stray flat `kind` is now absorbed or ignored, never a
    refusal, and no message on this path names a tool field."""

    def test_flat_create_next_to_the_same_create_stages_one_batch(self):
        build = schedule_chat.ProposalBuild(
            kind="proposal", proposal_id=PROPOSAL_ID, pill_text="Batch pill",
        )
        captured = {}

        async def fake_build_batch_proposal(conn, **kwargs):
            captured.update(kwargs)
            return build

        with mock.patch.object(schedule_chat, "build_batch_proposal", fake_build_batch_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={
                    # The flat fields echo the create that is already in the
                    # batch — one shift was asked for, one must be staged.
                    "kind": "create", "label": "barista", "date": "2026-08-23",
                    "start_time": "07:00", "end_time": "15:00", "count": 2,
                    "changes": [
                        {"kind": "cancel", "target_date": "2026-08-23", "target_time_hint": "06:00"},
                        {"kind": "create", "label": "barista", "date": "2026-08-23",
                         "start_time": "07:00", "end_time": "15:00", "count": 2},
                    ],
                },
            ))

        assert result["status"] == "ready"
        assert result["operation_count"] == 2
        assert result["operation_summary"] == {"cancel": 1, "create": 1}
        assert len(captured["edit_requests"]) == 1
        assert len(captured["shift_requests"]) == 1

    def test_stray_flat_create_over_pure_edits_stages_the_edits(self):
        """No new shift anywhere in the request — the flat `kind` is a bare
        enum the model filled in, and the reassign must still stage."""
        build = schedule_chat.ProposalBuild(
            kind="edit", proposal_id=PROPOSAL_ID, pill_text="pill",
        )

        async def fake_build_edit_proposal(*args, **kwargs):
            return build

        async def should_not_batch(*args, **kwargs):
            raise AssertionError("a pure edit batch must not become a create")

        with (
            mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal),
            mock.patch.object(schedule_chat, "build_batch_proposal", should_not_batch),
        ):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"kind": "create", "changes": [
                    {"kind": "reassign", "target_employee_name": "Aisha Kim",
                     "to_employee_name": "Elena Iyer", "target_date": "2026-08-24"},
                ]},
            ))

        assert result["status"] == "ready"
        assert result["operation_count"] == 1
        assert result["operation_summary"] == {"reassign": 1}

    def test_a_flat_create_the_batch_does_not_carry_is_absorbed_not_dropped(self):
        """When `changes` is populated the flat args are otherwise discarded,
        so a create that lives only there has to ride the batch — dropping it
        would silently lose a shift the manager asked for."""
        build = schedule_chat.ProposalBuild(
            kind="proposal", proposal_id=PROPOSAL_ID, pill_text="Batch pill",
        )
        captured = {}

        async def fake_build_batch_proposal(conn, **kwargs):
            captured.update(kwargs)
            return build

        with mock.patch.object(schedule_chat, "build_batch_proposal", fake_build_batch_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={
                    "kind": "create", "label": "closer", "date": "2026-08-24",
                    "start_time": "15:00", "end_time": "23:00",
                    "changes": [
                        {"kind": "cancel", "target_date": "2026-08-24", "target_time_hint": "14:00"},
                    ],
                },
            ))

        assert result["status"] == "ready"
        assert result["operation_summary"] == {"cancel": 1, "create": 1}
        assert len(captured["shift_requests"]) == 1
        assert captured["shift_requests"][0]["date"] == "2026-08-24"
        assert captured["shift_requests"][0]["start_time"] == "15:00"
        assert captured["shift_requests"][0]["label"] == "closer"

    def test_an_absorbed_create_counts_toward_the_cap(self):
        """Absorption happens before the batch is weighed, so it can't smuggle
        a 41st operation past the reviewability cap."""
        async def should_not_build(*args, **kwargs):
            raise AssertionError("an over-cap batch must not persist a proposal")

        changes = [
            {"kind": "cancel", "target_date": f"2026-08-{23 + index // 8:02d}",
             "target_time_hint": f"{8 + index % 8:02d}:00"}
            for index in range(MAX_BATCH_OPERATIONS)
        ]
        with (
            mock.patch.object(schedule_chat, "build_edit_proposal", should_not_build),
            mock.patch.object(schedule_chat, "build_batch_proposal", should_not_build),
        ):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"kind": "create", "label": "barista", "date": "2026-08-29",
                      "start_time": "07:00", "end_time": "15:00", "changes": changes},
            ))

        assert result["status"] == "clarify"
        assert f"{MAX_BATCH_OPERATIONS + 1} schedule operations" in result["message"]

    def test_a_partial_flat_create_beside_the_real_one_is_a_summary_not_a_shift(self):
        """The flat fields are an intent SUMMARY, so they are usually partial:
        `kind='create', label, count` with the date and times only inside
        `changes`. The identity match then misses, and appending the partial
        copy re-created the exact dead end this path exists to fix — one
        terminal refusal, the whole correction lost with nothing staged."""
        build = schedule_chat.ProposalBuild(
            kind="proposal", proposal_id=PROPOSAL_ID, pill_text="Batch pill",
        )
        captured = {}

        async def fake_build_batch_proposal(conn, **kwargs):
            captured.update(kwargs)
            return build

        with mock.patch.object(schedule_chat, "build_batch_proposal", fake_build_batch_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={
                    "kind": "create", "label": "barista", "count": 2,
                    "changes": [
                        {"kind": "cancel", "target_date": "2026-08-23", "target_time_hint": "06:00"},
                        {"kind": "create", "label": "barista", "date": "2026-08-23",
                         "start_time": "07:00", "end_time": "15:00", "count": 2},
                    ],
                },
            ))

        assert result["status"] == "ready"
        assert result["operation_count"] == 2
        assert result["operation_summary"] == {"cancel": 1, "create": 1}
        assert len(captured["shift_requests"]) == 1

    def test_an_unbuildable_flat_create_with_no_create_anywhere_still_refuses(self):
        """Ignoring a partial flat create is only safe because `changes`
        carries the shift. With no create anywhere the manager really did ask
        for one we cannot build, so the refusal stands — worded for the shift,
        never indexed as a "Schedule change 2" the batch does not contain."""
        async def should_not_build(*args, **kwargs):
            raise AssertionError("an unbuildable create must not persist a proposal")

        with (
            mock.patch.object(schedule_chat, "build_edit_proposal", should_not_build),
            mock.patch.object(schedule_chat, "build_batch_proposal", should_not_build),
        ):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"kind": "create", "label": "barista", "count": 2, "changes": [
                    {"kind": "cancel", "target_date": "2026-08-23", "target_time_hint": "06:00"},
                ]},
            ))

        assert result["status"] == "clarify"
        assert "Schedule change" not in result["message"]
        assert "date" in result["message"] and "start time" in result["message"]

    def test_a_formatting_near_miss_between_the_two_copies_stages_one_shift(self):
        """The flat copy and the `changes` copy are two independent model
        spellings of ONE shift. Compared raw, `7:00` vs `07:00` staged both —
        the manager confirms once and gets two identical shifts out of one
        transaction."""
        near_misses = [
            {"start_time": "7:00"}, {"start_time": "07:00:00"},
            {"end_time": "15:00:00"}, {"date": "2026-8-23"},
        ]
        for spelling in near_misses:
            with self.subTest(spelling=spelling):
                build = schedule_chat.ProposalBuild(
                    kind="proposal", proposal_id=PROPOSAL_ID, pill_text="Batch pill",
                )
                captured = {}

                async def fake_build_batch_proposal(conn, _c=captured, _b=build, **kwargs):
                    _c.update(kwargs)
                    return _b

                flat = {"kind": "create", "label": "barista", "date": "2026-08-23",
                        "start_time": "07:00", "end_time": "15:00", **spelling}
                with mock.patch.object(
                    schedule_chat, "build_batch_proposal", fake_build_batch_proposal,
                ):
                    result = _run(schedule_skill.propose(
                        conn=None, company_id="c1", actor_user_id="u1",
                        args={**flat, "changes": [
                            {"kind": "cancel", "target_date": "2026-08-23",
                             "target_time_hint": "06:00"},
                            {"kind": "create", "label": "barista", "date": "2026-08-23",
                             "start_time": "07:00", "end_time": "15:00"},
                        ]},
                    ))

                assert result["status"] == "ready"
                assert result["operation_summary"] == {"cancel": 1, "create": 1}
                assert len(captured["shift_requests"]) == 1

    def test_the_dropped_flat_copy_still_contributes_its_staffing_detail(self):
        """De-duping keeps the `changes` item, so a pinned employee or a
        headcount the model wrote only into the flat copy used to vanish —
        the same silent loss absorption was added to prevent."""
        build = schedule_chat.ProposalBuild(
            kind="proposal", proposal_id=PROPOSAL_ID, pill_text="Batch pill",
        )
        captured = {}

        async def fake_build_batch_proposal(conn, **kwargs):
            captured.update(kwargs)
            return build

        with mock.patch.object(schedule_chat, "build_batch_proposal", fake_build_batch_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={
                    "kind": "create", "label": "barista", "date": "2026-08-23",
                    "start_time": "07:00", "end_time": "15:00", "count": 2,
                    "employee_names": ["Aisha Kim"],
                    "changes": [
                        {"kind": "cancel", "target_date": "2026-08-23", "target_time_hint": "06:00"},
                        {"kind": "create", "label": "barista", "date": "2026-08-23",
                         "start_time": "07:00", "end_time": "15:00"},
                    ],
                },
            ))

        assert result["status"] == "ready"
        assert len(captured["shift_requests"]) == 1
        staged = captured["shift_requests"][0]
        assert staged["count"] == 2
        assert staged["employee_name_hints"] == ["Aisha Kim"]

    def test_an_absorbed_create_buckets_under_the_day_its_shift_is_on(self):
        """`_coerce_tool_shift_request` reads `date or target_date` while
        `schedule_batch.item_day` reads `target_date or date`. A stray
        top-level `target_date` made the two disagree, so the split plan the
        manager reads back named a day the shift is not on."""
        absorbed = schedule_skill._flat_create_change({
            "kind": "create", "label": "barista", "date": "2026-08-23",
            "target_date": "2026-08-30", "start_time": "07:00", "end_time": "15:00",
        })
        assert item_day(absorbed) == _date(2026, 8, 23)
        assert schedule_skill._coerce_tool_shift_request(absorbed)["date"] == "2026-08-23"

    def test_no_coercion_message_names_a_tool_field(self):
        """Every string this returns is relayed to the manager verbatim. The
        old refusal quoted the tool schema at them; nothing here may."""
        cases = [
            {"kind": "create", "changes": {"kind": "cancel"}},
            {"kind": "create", "changes": [{"kind": "create", "label": "barista"}]},
            {"kind": "create", "label": "barista", "changes": [{"kind": "cancel"}]},
            {"changes": [{"kind": "create", "date": "2026-08-23"}]},
            {"changes": ["not a change"]},
        ]
        # An edit the resolver can't pin to a shift takes the last copy path.
        unresolvable = mock.Mock(coerce_edit_request=mock.Mock(return_value=None))
        cases_with_chat = [(_FakeScheduleChat(), args) for args in cases]
        cases_with_chat.append((unresolvable, {"changes": [{"kind": "reassign"}]}))
        for chat, args in cases_with_chat:
            _, _, error = schedule_skill._coerce_tool_batch(chat, args)
            assert error, args
            assert "`" not in error, error
            assert "kind: create" not in error, error
            assert "Put the new shift inside" not in error, error


class _ConnCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_a):
        return False


class _ProposalConn:
    def __init__(self, row):
        self.row = row
        self.queries = []

    async def fetchrow(self, query, *_a, **_k):
        self.queries.append(query)
        return self.row


def _batch_row(status="proposed"):
    return {
        "id": PROPOSAL_ID, "company_id": "c1", "channel_id": None, "status": status,
        "proposal": {"kind": "batch", "edit": {"ops": [{"kind": "cancel"}]}, "create": {"shifts": []}},
    }


class TestExecuteBatchDispatch(unittest.TestCase):
    """The confirm turn routes a `kind='batch'` row to the batch executor and
    reports its rollback failures as "nothing was applied" — never as a
    partial success, never through the agent's generic failure path."""

    def _run_execute(self, row, executor):
        import app.database as database
        import app.core.feature_flags as feature_flags

        async def fake_features(*_a, **_k):
            return {"employee_schedule": True}

        with (
            mock.patch.object(
                database, "get_connection", lambda: _ConnCtx(_ProposalConn(row)),
            ),
            mock.patch.object(feature_flags, "get_company_features", fake_features),
            mock.patch.object(schedule_chat, "execute_batch_proposal", executor),
            mock.patch.object(
                schedule_chat, "execute_edit_proposal",
                mock.AsyncMock(side_effect=AssertionError("wrong executor")),
            ),
            mock.patch.object(
                schedule_chat, "execute_proposal",
                mock.AsyncMock(side_effect=AssertionError("wrong executor")),
            ),
        ):
            return _run(schedule_skill.execute(
                company_id="c1", actor_user_id="u1",
                action=_change(proposal_id=PROPOSAL_ID),
            ))

    def test_batch_row_dispatches_to_the_batch_executor(self):
        captured = {}

        async def fake_execute_batch(conn, **kwargs):
            captured.update(kwargs)
            return schedule_chat.ProposalExecutionReceipt(
                text="✅ Done — 28 changes are live\n✅ Done — 7 shifts are live",
                touched_shift_ids=(uuid4(),),
            )

        result = self._run_execute(_batch_row(), fake_execute_batch)
        assert result["status"] == "created"
        assert result["record_id"] == PROPOSAL_ID
        assert "28 changes" in result["message"] and "7 shifts" in result["message"]
        assert captured["proposal_row"]["proposal"]["kind"] == "batch"

    def test_scope_failure_reports_nothing_applied(self):
        async def failing(conn, **kwargs):
            raise schedule_chat.ProposalScopeError(
                "That schedule proposal is outside the selected schedule week.",
            )

        result = self._run_execute(_batch_row(), failing)
        assert result["status"] == "error"
        assert result["message"].startswith("Nothing was applied")
        assert "outside the selected schedule week" in result["message"]

    def test_single_create_scope_failure_preserves_the_actionable_message(self):
        import app.database as database
        import app.core.feature_flags as feature_flags

        row = {
            **_batch_row(),
            "proposal": {"shifts": [{"starts_at": "2026-08-23T07:00:00+00:00"}]},
        }

        async def fake_features(*_a, **_k):
            return {"employee_schedule": True}

        with (
            mock.patch.object(
                database, "get_connection", lambda: _ConnCtx(_ProposalConn(row)),
            ),
            mock.patch.object(feature_flags, "get_company_features", fake_features),
            mock.patch.object(
                schedule_chat, "execute_proposal",
                mock.AsyncMock(side_effect=schedule_chat.ProposalScopeError(
                    "That schedule proposal is outside the selected schedule week.",
                )),
            ),
        ):
            result = _run(schedule_skill.execute(
                company_id="c1", actor_user_id="u1",
                action=_change(proposal_id=PROPOSAL_ID),
            ))

        assert result["status"] == "error"
        assert result["message"] == (
            "Nothing was applied — That schedule proposal is outside the selected schedule week."
        )

    def test_unexpected_failure_in_a_batch_reports_rollback(self):
        async def failing(conn, **kwargs):
            raise RuntimeError("boom")

        result = self._run_execute(_batch_row(), failing)
        assert result["status"] == "error"
        assert "rolled back" in result["message"]

    def test_unexpected_failure_in_a_single_edit_reports_rollback(self):
        import app.database as database
        import app.core.feature_flags as feature_flags

        row = {
            **_batch_row(),
            "proposal": {"kind": "edit", "ops": [{"kind": "cancel"}]},
        }

        async def fake_features(*_a, **_k):
            return {"employee_schedule": True}

        with (
            mock.patch.object(
                database, "get_connection", lambda: _ConnCtx(_ProposalConn(row)),
            ),
            mock.patch.object(feature_flags, "get_company_features", fake_features),
            mock.patch.object(
                schedule_chat, "execute_edit_proposal",
                mock.AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            result = _run(schedule_skill.execute(
                company_id="c1", actor_user_id="u1",
                action=_change(proposal_id=PROPOSAL_ID),
            ))

        assert result["status"] == "error"
        assert "Nothing was applied" in result["message"]
        assert "rolled back" in result["message"]

    def test_lost_commit_ack_recovers_the_durable_success_receipt(self):
        import app.database as database
        import app.core.feature_flags as feature_flags

        shift_id = uuid4()
        row = _batch_row()
        connections = []

        async def fake_features(*_a, **_k):
            return {"employee_schedule": True}

        async def committed_then_disconnected(conn, **_kwargs):
            row["status"] = "confirmed"
            row["created_shift_ids"] = [shift_id]
            row["proposal"] = {
                **row["proposal"],
                "execution_receipt": {
                    "version": 1,
                    "message": "Schedule updated.",
                    "touched_shift_ids": [str(shift_id)],
                },
            }
            raise ConnectionError("commit acknowledgement lost")

        def fake_connection():
            conn = _ProposalConn(row)
            connections.append(conn)
            return _ConnCtx(conn)

        with (
            mock.patch.object(database, "get_connection", fake_connection),
            mock.patch.object(feature_flags, "get_company_features", fake_features),
            mock.patch.object(
                schedule_chat, "execute_batch_proposal", committed_then_disconnected,
            ),
        ):
            result = _run(schedule_skill.execute(
                company_id="c1", actor_user_id="u1",
                action=_change(proposal_id=PROPOSAL_ID),
            ))

        assert result["status"] == "created"
        assert result["message"] == "Schedule updated."
        assert result["verified"] is True
        assert len(connections) == 2 and connections[0] is not connections[1]
        assert "FOR UPDATE" in connections[1].queries[0]

    def test_confirmed_without_a_valid_receipt_is_reported_as_unknown(self):
        import app.database as database
        import app.core.feature_flags as feature_flags

        row = _batch_row()

        async def fake_features(*_a, **_k):
            return {"employee_schedule": True}

        async def committed_without_receipt(conn, **_kwargs):
            row["status"] = "confirmed"
            row["created_shift_ids"] = [uuid4()]
            raise ConnectionError("commit acknowledgement lost")

        with (
            mock.patch.object(
                database, "get_connection", lambda: _ConnCtx(_ProposalConn(row)),
            ),
            mock.patch.object(feature_flags, "get_company_features", fake_features),
            mock.patch.object(
                schedule_chat, "execute_batch_proposal", committed_without_receipt,
            ),
        ):
            result = _run(schedule_skill.execute(
                company_id="c1", actor_user_id="u1",
                action=_change(proposal_id=PROPOSAL_ID),
            ))

        assert result["status"] == "error"
        assert "outcome could not be verified" in result["message"]
        assert "Nothing was applied" not in result["message"]

    def test_already_claimed_batch_is_refused(self):
        async def failing(conn, **kwargs):
            raise schedule_chat.ProposalExecutionClaimError(
                "That proposal is already being applied or is no longer available.",
            )

        result = self._run_execute(_batch_row(), failing)
        assert result["status"] == "error"
        assert "already being applied" in result["message"]

    def test_stale_batch_row_is_refused_before_any_executor(self):
        result = self._run_execute(
            _batch_row(status="confirmed"),
            mock.AsyncMock(side_effect=AssertionError("must not run")),
        )
        assert result["status"] == "error"


class TestPersistedExecutionReceipt(unittest.TestCase):
    def test_confirmed_receipt_round_trips(self):
        shift_id = uuid4()
        row = {
            "status": "confirmed",
            "created_shift_ids": [shift_id],
            "proposal": {"execution_receipt": {
                "version": 1,
                "message": "Schedule updated.",
                "touched_shift_ids": [str(shift_id)],
            }},
        }
        receipt = schedule_skill._receipt_from_row(row, schedule_chat)
        assert receipt == schedule_chat.ProposalExecutionReceipt(
            text="Schedule updated.", touched_shift_ids=(shift_id,),
        )

    def test_receipt_and_finalized_ids_must_match(self):
        row = {
            "status": "confirmed",
            "created_shift_ids": [uuid4()],
            "proposal": {"execution_receipt": {
                "version": 1,
                "message": "Schedule updated.",
                "touched_shift_ids": [str(uuid4())],
            }},
        }
        assert schedule_skill._receipt_from_row(row, schedule_chat) is None

    def test_confirmed_no_op_is_not_reported_as_success(self):
        result = schedule_skill._execution_response(
            schedule_chat.ProposalExecutionReceipt(
                text="No edits applied.", touched_shift_ids=(),
            ),
            proposal_id=PROPOSAL_ID,
        )
        assert result["status"] == "error"
        assert "No edits applied" in result["message"]
        assert "None of the requested shifts changed" in result["message"]


class _VacantConn:
    """Fake for `_all_vacant_shift_requests`: returns N open shifts, four a day."""

    def __init__(self, count):
        from datetime import datetime, timedelta, timezone
        base = datetime(2026, 8, 23, 6, tzinfo=timezone.utc)
        self.rows = [
            {"id": f"shift-{i}", "starts_at": base + timedelta(days=i // 4, hours=4 * (i % 4))}
            for i in range(count)
        ]
        self.queries = []

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        return self.rows

    async def fetchval(self, *_a, **_k):
        return "Downtown"


def _review(staged, rejected):
    return {
        "proposal_id": PROPOSAL_ID, "kind": "edit", "compliance_status": "unmapped",
        "assignments": [{"shift_id": f"shift-{i}", "op": "assign", "verdict": "ok", "reasons": []} for i in range(staged)],
        "rejected": [{"shift_id": f"shift-{staged + i}", "role": "Shift Lead", "reasons": [
            {"code": "intra_batch_overlap", "message": "would overlap …", "policy": False}]} for i in range(rejected)],
        "unfilled": [], "employees": [{"employee_id": "e1", "name": "Dana Reyes", "before": {}, "after": {},
                                       "warnings": ["only 0.0h rest next to another shift (policy: 8h minimum)"]}],
        "advisories": [], "findings": [],
        "jurisdiction": {"state": "TX", "status": "unmapped", "message": "Legality was NOT verified for TX — …"},
    }


class TestAllVacantGoesThroughTheGuard(unittest.TestCase):
    """The reported failure path: one named person × every open shift. The
    server now (a) caps it like any batch and (b) returns what the guard
    refused, so the model can only describe what was actually staged."""

    def _match(self):
        async def fake_match(conn, company_id, hint, location_id):
            return {"employee": {"id": "e1", "first_name": "Dana", "last_name": "Reyes"}}
        return fake_match

    def test_nine_open_shifts_report_staged_and_rejected_counts(self):
        from datetime import date
        from uuid import UUID as _UUID
        conn = _VacantConn(9)
        captured = {}

        async def fake_build_edit_proposal(conn_, **kwargs):
            captured.update(kwargs)
            return schedule_chat.ProposalBuild(
                kind="proposal", proposal_id=PROPOSAL_ID, pill_text="pill", review=_review(4, 5),
            )

        with (
            mock.patch.object(schedule_chat, "_match_single_employee", self._match()),
            mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal),
        ):
            result = _run(schedule_skill.propose(
                conn=conn, company_id="c1", actor_user_id="u1",
                args={"all_vacant_shifts": True, "to_employee_name": "Dana"},
                location_id=_UUID("c0ffeeee-0001-4001-8001-000000000001"),
                week_start=date(2026, 8, 23), week_end=date(2026, 8, 29),
            ))

        assert len(captured["parsed"]["edit_requests"]) == 9
        assert {r["kind"] for r in captured["parsed"]["edit_requests"]} == {"assign"}
        assert result["status"] == "ready"
        assert result["operation_count"] == 4            # what was STAGED, not what was asked
        assert result["operation_summary"] == {"assign": 4}
        assert result["rejected_count"] == 5
        assert result["compliance_status"] == "unmapped"
        assert result["review"]["employees"][0]["warnings"][0].startswith("only 0.0h rest")

    def test_all_vacant_respects_the_batch_cap_with_a_split_plan(self):
        from datetime import date
        from uuid import UUID as _UUID
        conn = _VacantConn(MAX_BATCH_OPERATIONS + 8)

        async def should_not_build(*a, **k):
            raise AssertionError("over-cap bulk must not build")

        with (
            mock.patch.object(schedule_chat, "_match_single_employee", self._match()),
            mock.patch.object(schedule_chat, "build_edit_proposal", should_not_build),
        ):
            result = _run(schedule_skill.propose(
                conn=conn, company_id="c1", actor_user_id="u1",
                args={"all_vacant_shifts": True, "to_employee_name": "Dana"},
                location_id=_UUID("c0ffeeee-0001-4001-8001-000000000001"),
                week_start=date(2026, 8, 23), week_end=date(2026, 8, 29),
            ))
        assert result["status"] == "clarify"
        assert f"{MAX_BATCH_OPERATIONS + 8} schedule operations" in result["message"]
        assert "Smallest split is 2 batches" in result["message"]

    def test_a_refused_clarify_is_relayed_without_the_ambiguity_hint(self):
        build = schedule_chat.ProposalBuild(
            kind="clarify", proposal_id=PROPOSAL_ID, clarify_kind="refused",
            pill_text=schedule_chat.clarify_text(
                "I couldn't stage any of those — Dana Reyes on the Shift Lead Sun Aug 23: already on the Opener. "
                "Pick someone else for those shifts, or tell me which to drop.", []),
        )

        async def fake_build_edit_proposal(*a, **k):
            return build

        with mock.patch.object(schedule_chat, "build_edit_proposal", fake_build_edit_proposal):
            result = _run(schedule_skill.propose(
                conn=None, company_id="c1", actor_user_id="u1",
                args={"kind": "assign", "to_employee_name": "Dana", "target_date": "2026-08-23"},
            ))
        assert result["status"] == "clarify"
        assert "couldn't stage any of those" in result["message"]
        assert "Reply with the shift time" not in result["message"]
        assert "Just reply to this message" not in result["message"]


# ── fill_vacant_shifts: the SERVER picks people (2026-09-07) ─────────────────

DANA_ID = "33333333-3333-3333-3333-000000000001"
BEN_ID = "33333333-3333-3333-3333-000000000002"


def _fill_plan(assignments, unfilled=(), *, status="ready", message=None):
    from datetime import datetime, timezone
    plan = {
        "status": status, "message": message, "assignments": list(assignments), "unfilled": list(unfilled),
        "hours_by_employee": {}, "metrics": {}, "roster_size": 2, "demand_size": len(assignments) + len(unfilled),
        "jurisdiction": {"state": "CA", "status": "curated", "message": "Scheduling law for CA is on file (hand-curated)."},
    }
    if unfilled:
        # The planner hands back real datetimes here; the skill must serialize them.
        plan["unfilled"] = [{**item, "starts_at": datetime(2026, 8, 23, 14, tzinfo=timezone.utc),
                             "ends_at": datetime(2026, 8, 23, 22, tzinfo=timezone.utc)} for item in unfilled]
    return plan


def _planned(shift_id, name, employee_id):
    return {"shift_id": shift_id, "role": "Shift Lead", "starts_at": "2026-08-23T06:00:00+00:00",
            "ends_at": "2026-08-23T14:00:00+00:00", "employee_id": employee_id, "employee_name": name,
            "reason": "Available and qualified; scheduled hours become 8h."}


class TestFillVacantShifts(unittest.TestCase):
    """`fill_vacant_shifts=true` → `week_builder.plan_vacant_fill` picks the
    people → the SAME `build_edit_proposal` stages them (guard, pill, confirm).
    The model never names anyone for a fill."""

    LOCATION = "c0ffeeee-0001-4001-8001-000000000001"

    def _propose(self, args, *, plan, build=None, match=None, location=True):
        from datetime import date
        from uuid import UUID as _UUID
        from app.matcha.services.scheduling import week_builder
        captured = {"plan": None, "build": None}
        people = {"Dana": {"id": _UUID(DANA_ID), "first_name": "Dana", "last_name": "Reyes"},
                  "Ben": {"id": _UUID(BEN_ID), "first_name": "Ben", "last_name": "Ortiz"}}

        async def fake_plan(conn, **kwargs):
            captured["plan"] = kwargs
            return plan

        async def fake_build(conn_, **kwargs):
            captured["build"] = kwargs
            return build or schedule_chat.ProposalBuild(
                kind="proposal", proposal_id=PROPOSAL_ID, pill_text="pill", review=_review(2, 0),
            )

        async def fake_match(conn, company_id, hint, location_id):
            if match and hint in match:
                return match[hint]
            return {"employee": people[hint]}

        with (
            mock.patch.object(week_builder, "plan_vacant_fill", fake_plan),
            mock.patch.object(schedule_chat, "_match_single_employee", fake_match),
            mock.patch.object(schedule_chat, "build_edit_proposal", fake_build),
        ):
            result = _run(schedule_skill.propose(
                conn=_VacantConn(0), company_id="c1", actor_user_id="u1", args=args,
                location_id=_UUID(self.LOCATION) if location else None,
                week_start=date(2026, 8, 23) if location else None,
                week_end=date(2026, 8, 29) if location else None,
            ))
        return result, captured

    def test_the_server_picks_people_and_the_guard_stages_them(self):
        from datetime import date
        from uuid import UUID as _UUID
        shift_uuid = "55555555-5555-4555-8555-000000000001"
        plan = _fill_plan(
            [_planned("shift-0", "Dana Reyes", DANA_ID), _planned("shift-1", "Ben Ortiz", BEN_ID)],
            [{"shift_id": "shift-2", "role": "Shift Lead", "reason": "policy: second shift that day",
              "exclusions": {"policy: second shift that day": 2}}],
        )
        result, captured = self._propose({
            "fill_vacant_shifts": True, "fill_job_name": " shift lead ", "exclude_employee_names": ["Ben", ""],
            "fill_shift_ids": [shift_uuid], "allow_split_shift": True,
        }, plan=plan)

        assert captured["plan"] == {
            "company_id": "c1", "location_id": _UUID(self.LOCATION),
            "week_start": date(2026, 8, 23), "week_end": date(2026, 8, 29),
            "role_hint": "shift lead", "shift_ids": [_UUID(shift_uuid)],
            "only_employee_ids": None, "exclude_employee_ids": [_UUID(BEN_ID)], "allow_split_shift": True,
        }
        assert captured["build"]["parsed"]["edit_requests"] == [
            {"kind": "assign", "target_shift_id": "shift-0", "to_employee_name": "Dana Reyes", "to_employee_id": DANA_ID},
            {"kind": "assign", "target_shift_id": "shift-1", "to_employee_name": "Ben Ortiz", "to_employee_id": BEN_ID},
        ]
        assert captured["build"]["surface"] == "editor"
        assert captured["build"]["shift_statuses"] == ("draft", "published")
        assert result["status"] == "ready"
        assert result["operation_count"] == 2 and result["operation_summary"] == {"assign": 2}
        assert result["unfilled_count"] == 1
        assert result["review"]["unfilled"] == [{
            "shift_id": "shift-2", "role": "Shift Lead", "reason": "policy: second shift that day",
            "exclusions": {"policy: second shift that day": 2},
            "starts_at": "2026-08-23T14:00:00+00:00", "ends_at": "2026-08-23T22:00:00+00:00",
        }]

    def test_naming_one_person_narrows_the_roster_instead_of_multiplying_the_name(self):
        from uuid import UUID as _UUID
        result, captured = self._propose(
            {"fill_vacant_shifts": True, "to_employee_name": "Dana"},
            plan=_fill_plan([_planned("shift-0", "Dana Reyes", DANA_ID)]),
        )
        assert captured["plan"]["only_employee_ids"] == [_UUID(DANA_ID)]
        assert captured["plan"]["exclude_employee_ids"] is None
        assert captured["plan"]["role_hint"] is None and captured["plan"]["shift_ids"] is None
        assert captured["plan"]["allow_split_shift"] is False
        assert result["status"] == "ready" and result["unfilled_count"] == 0

    def test_nothing_fillable_is_a_clarify_that_names_the_reasons(self):
        plan = _fill_plan([], [
            {"shift_id": "a", "role": "Shift Lead", "reason": "policy: second shift that day", "exclusions": {}},
            {"shift_id": "b", "role": "Opener", "reason": "not qualified for the shift job", "exclusions": {}},
        ])
        result, captured = self._propose({"fill_vacant_shifts": True}, plan=plan)
        assert result["status"] == "clarify"
        assert result["message"].startswith("I couldn't fill any of those shifts: Shift Lead 2026-08-23 14:00 — policy: second shift that day; Opener 2026-08-23 14:00 — not qualified for the shift job.")
        assert "allow a split shift" in result["message"]
        assert captured["build"] is None

    def test_a_planner_clarify_or_refusal_is_relayed_verbatim(self):
        result, captured = self._propose(
            {"fill_vacant_shifts": True, "fill_job_name": "barista"},
            plan=_fill_plan([], status="clarify", message='There are no open shifts matching "barista" in this week to fill.'),
        )
        assert result == {"status": "clarify", "message": 'There are no open shifts matching "barista" in this week to fill.'}
        assert captured["build"] is None

    def test_a_fill_needs_the_scoped_schedule_workspace(self):
        result, captured = self._propose({"fill_vacant_shifts": True}, plan=_fill_plan([]), location=False)
        assert result["status"] == "clarify"
        assert "requires a scoped schedule workspace" in result["message"]
        assert captured["plan"] is None

    def test_an_unknown_or_ambiguous_name_stops_before_planning(self):
        result, captured = self._propose(
            {"fill_vacant_shifts": True, "exclude_employee_names": ["Zed"]}, plan=_fill_plan([]),
            match={"Zed": {"none": "I couldn't find anyone named Zed at this location."}},
        )
        assert result == {"status": "clarify", "message": "I couldn't find anyone named Zed at this location."}
        assert captured["plan"] is None
        result, captured = self._propose(
            {"fill_vacant_shifts": True, "to_employee_name": "Sam"}, plan=_fill_plan([]),
            match={"Sam": {"ambiguous": ["Sam Lee", "Sam Park"]}},
        )
        assert result["status"] == "clarify" and "Which Sam did you mean? Sam Lee, Sam Park" in result["message"]

    def test_a_bad_shift_id_is_a_clarify_not_a_crash(self):
        result, captured = self._propose({"fill_vacant_shifts": True, "fill_shift_ids": ["shift-9"]}, plan=_fill_plan([]))
        assert result["status"] == "clarify" and "use ids from get_schedule_overview" in result["message"]
        assert captured["plan"] is None

    def test_the_fill_fields_survive_the_staged_whitelist_and_the_tool_schema(self):
        fields = set(_HR_OPS_TOOL_SPECS["propose_schedule_change"]["fields"])
        new = {"fill_vacant_shifts", "fill_job_name", "fill_shift_ids", "exclude_employee_names", "allow_split_shift"}
        assert new <= fields, new - fields
        properties = TOOLS_BY_NAME["propose_schedule_change"].declaration.parameters.properties
        assert new <= set(properties)
        hints = TOOLS_BY_NAME["propose_schedule_change"].intent_hints
        assert any("fill" in hint and "open" in hint for hint in hints)

    def test_fill_refuses_over_cap_before_building_a_proposal(self):
        result, captured = self._propose({"fill_vacant_shifts": True}, plan=_fill_plan([
            _planned(f"shift-{i}", "Dana Reyes", DANA_ID) for i in range(41)
        ]))
        assert result["status"] == "clarify"
        assert "41 schedule operations" in result["message"]
        assert captured["build"] is None


def test_coverage_editor_includes_drafts_and_channel_stays_published_only():
    from contextlib import asynccontextmanager
    from uuid import uuid4
    from app.matcha.services.scheduling import coverage

    @asynccontextmanager
    async def connection():
        yield object()

    finder = mock.AsyncMock(return_value={"shifts": []})
    with mock.patch("app.database.get_connection", connection), mock.patch.object(coverage, "find_coverage_candidates", finder):
        for surface, statuses in ((True, ("draft", "published")), (False, ("published",))):
            _run(schedule_skill.find_coverage(
                company_id=uuid4(), role="client", features={"employee_schedule": True},
                date_str="2026-08-23", role_hint=None, location_id=uuid4(), schedule_surface=surface,
            ))
            assert finder.await_args.kwargs["statuses"] == statuses


class TestResolvedCreateCounts(unittest.TestCase):
    def test_two_new_shifts_count_twice_even_with_multiple_assignees_and_no_ids(self):
        from app.matcha.services.scheduling.schedule_review import build_review
        shifts = [{"label": "lead", "starts_at": f"2026-08-{day}T06:00:00+00:00",
                   "ends_at": f"2026-08-{day}T14:00:00+00:00", "assignees": people}
                  for day, people in ((23, [{"employee_id": "a"}, {"employee_id": "b"}]), (24, []))]
        review = build_review({"kind": "batch", "create": {"shifts": shifts},
                               "jurisdiction": {"state": "CA", "status": "curated"}})
        build = schedule_chat.ProposalBuild(kind="proposal", proposal_id=PROPOSAL_ID,
                                            pill_text="two shifts", review=review)
        with mock.patch.object(schedule_chat, "build_batch_proposal", mock.AsyncMock(return_value=build)):
            result = _run(schedule_skill.propose(
                None, company_id="c1", actor_user_id="u1", args={"changes": [
                    {"kind": "create", "label": "lead", "date": f"2026-08-{day}",
                     "start_time": "06:00", "end_time": "14:00"} for day in (23, 24)
                ]},
            ))
        assert result["status"] == "ready"
        assert len(review["assignments"]) == 3  # not an operation count
        assert all(a["shift_id"] is None for a in review["assignments"])
        assert result["operation_count"] == 2
        assert result["operation_summary"] == {"create": 2}

    def test_unavailable_rules_never_return_ready_on_create_batch_or_bulk_paths(self):
        from uuid import uuid4
        unavailable = {"state": "TX", "status": "unavailable", "message": "Rules unavailable."}
        resolved_op = {
            "kind": "assign", "shift_id": str(uuid4()), "location_id": str(uuid4()),
            "starts_at": "2026-08-23T06:00:00+00:00", "ends_at": "2026-08-23T14:00:00+00:00",
            "review": {"verdict": "ok", "reasons": []},
        }
        create_args = {"kind": "create", "label": "lead", "date": "2026-08-23",
                       "start_time": "06:00", "end_time": "14:00"}
        requests = [create_args, {"changes": [create_args]},
                    {"all_vacant_shifts": True, "to_employee_name": "Dana"}]
        for args in requests:
            with self.subTest(args=args):
                persist = mock.AsyncMock(return_value=uuid4())
                with (
                    mock.patch.object(schedule_chat, "_resolve_create_shifts", mock.AsyncMock(return_value={
                        "jurisdiction": unavailable, "shifts": [],
                    })),
                    mock.patch.object(schedule_chat, "_resolve_edit_ops", mock.AsyncMock(return_value=[resolved_op])),
                    mock.patch.object(schedule_chat, "_ops_jurisdiction", mock.AsyncMock(return_value=unavailable)),
                    mock.patch.object(schedule_chat, "_persist_proposal", persist),
                    mock.patch.object(schedule_skill, "_all_vacant_shift_requests", mock.AsyncMock(return_value=([{}], None))),
                ):
                    result = _run(schedule_skill.propose(None, company_id=uuid4(), actor_user_id=uuid4(), args=args))
                assert result["status"] == "clarify"
                assert "Rules unavailable" in result["message"]
                assert "Reply with the shift time" not in result["message"]
                assert all(c.kwargs["status"] == "clarifying" for c in persist.await_args_list)
