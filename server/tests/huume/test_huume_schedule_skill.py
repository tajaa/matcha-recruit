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
from unittest import mock

from app.matcha.services.huume.actions import evaluate_huume_action
from app.matcha.services.huume.agent import _HR_OPS_TOOL_SPECS, _build_hr_ops_staged
from app.matcha.services.huume.tools import TOOLS_BY_NAME
from app.matcha.services.huume import schedule_skill
from app.matcha.services.scheduling import schedule_chat

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

    def test_schema_declares_target_staffing_hint(self):
        # Two shifts can share the exact date AND time AND role (one
        # staffed, one open) — target_time_hint alone can't separate them.
        tool = TOOLS_BY_NAME["propose_schedule_change"]
        props = tool.declaration.parameters.properties
        assert "target_staffing_hint" in props
        assert set(props["target_staffing_hint"].enum) == {"staffed", "unstaffed"}

    def test_spec_fields_forward_target_staffing_hint(self):
        assert "target_staffing_hint" in _HR_OPS_TOOL_SPECS["propose_schedule_change"]["fields"]

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
    surfaces it as a refusal instead of staging an unconfirmable proposal.
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

        assert "error" in result
        assert "Aisha Kim" in result["error"]  # first option survived
        assert "unstaffed" in result["error"]  # second option survived
        assert "target_time_hint" in result["error"]
        assert "target_staffing_hint" in result["error"]
        # Channel-only UX ("reply to the pill") has no meaning in a thread,
        # and directly contradicts the very next sentence telling the model
        # to call the tool again.
        assert "Just reply to this message" not in result["error"]
