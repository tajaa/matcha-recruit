"""Pure-function tests for the Legal/Handbook Pilot chat tools' safety
envelope + prompt state (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_pilot_tools.py -q

Covers `evaluate_pilot_tool` (the route mount gates re-asserted on the chat
path), `filter_promotable_drafts` (the two-turn promote guard, mirroring
`resolve_plan_offer_id`), the new `build_state_block` sections, the tool
registry entries, and the pure citation resolver in `legal_skill`.
"""

from app.matcha.services.huume.actions import (
    PILOT_TOOL_REQUIRED_FEATURE,
    evaluate_pilot_tool,
    filter_promotable_drafts,
)
from app.matcha.services.huume.legal_skill import _citation_records
from app.matcha.services.huume.prompt import build_state_block, build_system_prompt
from app.matcha.services.huume.tools import TOOLS_BY_NAME

FEATURES_ON = {
    "huume": True, "matcha_work": True,
    "legal_defense": True, "handbook_pilot": True, "er_copilot": True,
}


class TestEvaluatePilotTool:
    def test_all_registered_tools_pass_with_flags_on(self):
        for tool in PILOT_TOOL_REQUIRED_FEATURE:
            assert evaluate_pilot_tool(tool=tool, role="client", features=FEATURES_ON) is None

    def test_admin_role_allowed(self):
        assert evaluate_pilot_tool(tool="ask_legal_pilot", role="admin", features=FEATURES_ON) is None

    def test_employee_role_refused(self):
        reason = evaluate_pilot_tool(tool="ask_legal_pilot", role="employee", features=FEATURES_ON)
        assert reason and "business admin" in reason

    def test_missing_role_refused(self):
        assert evaluate_pilot_tool(tool="ask_legal_pilot", role=None, features=FEATURES_ON)

    def test_legal_tools_require_legal_defense(self):
        features = {**FEATURES_ON, "legal_defense": False}
        for tool in ("list_legal_matters", "open_legal_matter", "ask_legal_pilot", "generate_legal_packet"):
            reason = evaluate_pilot_tool(tool=tool, role="client", features=features)
            assert reason and "legal_defense" in reason

    def test_handbook_tools_require_handbook_pilot(self):
        features = {**FEATURES_ON, "handbook_pilot": False}
        for tool in ("draft_handbook_content", "promote_handbook_drafts"):
            reason = evaluate_pilot_tool(tool=tool, role="client", features=features)
            assert reason and "handbook_pilot" in reason

    def test_er_tools_require_er_copilot(self):
        features = {**FEATURES_ON, "er_copilot": False}
        for tool in ("er_case_brief", "ask_er_copilot"):
            reason = evaluate_pilot_tool(tool=tool, role="client", features=features)
            assert reason and "er_copilot" in reason

    def test_huume_flag_required(self):
        reason = evaluate_pilot_tool(
            tool="draft_handbook_content", role="client", features={**FEATURES_ON, "huume": False},
        )
        assert reason and "Huume" in reason

    def test_matcha_work_flag_required(self):
        reason = evaluate_pilot_tool(
            tool="draft_handbook_content", role="client", features={**FEATURES_ON, "matcha_work": False},
        )
        assert reason and "Matcha Work" in reason

    def test_unknown_tool_refused(self):
        assert evaluate_pilot_tool(tool="not_a_tool", role="client", features=FEATURES_ON)

    def test_pilot_flag_check_runs_after_role(self):
        # An employee with every flag on is still refused — role outranks flags.
        reason = evaluate_pilot_tool(tool="ask_legal_pilot", role="employee", features=FEATURES_ON)
        assert "business admin" in reason


class TestFilterPromotableDrafts:
    def test_explicit_ids_pass_through(self):
        ids, err = filter_promotable_drafts(["d1", "d2"], set())
        assert ids == ["d1", "d2"] and err is None

    def test_this_turn_draft_blocked(self):
        ids, err = filter_promotable_drafts(["d1", "d2"], {"d2"})
        assert ids is None
        assert err and "this turn" in err

    def test_omitted_means_all_pending(self):
        ids, err = filter_promotable_drafts(None, {"d1"})
        assert ids is None and err is None

    def test_empty_list_means_all_pending(self):
        ids, err = filter_promotable_drafts([], {"d1"})
        assert ids is None and err is None


class TestPilotToolRegistry:
    def test_every_pilot_tool_is_declared(self):
        for tool in PILOT_TOOL_REQUIRED_FEATURE:
            assert tool in TOOLS_BY_NAME, f"{tool} missing from tools.py registry"

    def test_pilot_tool_kinds_are_valid(self):
        # kinds mirror the huume_steps CHECK constraint.
        for tool in PILOT_TOOL_REQUIRED_FEATURE:
            assert TOOLS_BY_NAME[tool].kind in ("read", "write", "staged")

    def test_system_prompt_lists_pilot_tools(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26", state_block="")
        for tool in PILOT_TOOL_REQUIRED_FEATURE:
            assert tool in prompt

    def test_system_prompt_carries_two_turn_promote_rule(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26", state_block="")
        assert "cannot be promoted THIS turn" in prompt


class TestStateBlockPilotSections:
    def test_active_legal_matter_rendered_with_id(self):
        block = build_state_block({"huume_legal": {"matter_id": "m-1", "title": "EEOC charge"}})
        assert "m-1" in block and "EEOC charge" in block

    def test_pending_handbook_drafts_rendered_with_ids(self):
        block = build_state_block({
            "huume_handbook": {
                "session_id": "s-1",
                "pending_drafts": [
                    {"draft_id": "d-1", "kind": "policy", "title": "PTO Policy"},
                    {"draft_id": "d-2", "kind": "handbook_section", "title": "Meal Breaks"},
                ],
            },
        })
        assert "d-1" in block and "PTO Policy" in block
        assert "d-2" in block and "Meal Breaks" in block

    def test_session_with_no_pending_drafts_still_noted(self):
        block = build_state_block({"huume_handbook": {"session_id": "s-1", "pending_drafts": []}})
        assert "no pending drafts" in block.lower()

    def test_empty_state_unchanged(self):
        block = build_state_block({})
        assert "nothing is currently staged" in block.lower()


class TestCitationRecords:
    INDEX = {
        "incident:abc": {"ref": "IR-42", "summary": "Slip near dock 3", "when": "2026-05-01",
                         "source": "incidents", "source_label": "Incidents"},
        "law:ca-breaks": {"ref": "CA meal breaks", "summary": "Meal period rules", "when": "",
                          "source": "law", "source_label": "Governing requirements"},
    }

    def test_resolves_known_cids_in_order(self):
        records = _citation_records(["incident:abc", "law:ca-breaks"], self.INDEX)
        assert [r["cid"] for r in records] == ["incident:abc", "law:ca-breaks"]
        assert records[0]["ref"] == "IR-42"
        assert records[0]["source_label"] == "Incidents"

    def test_unknown_cid_skipped_not_invented(self):
        records = _citation_records(["incident:abc", "law:made-up"], self.INDEX)
        assert [r["cid"] for r in records] == ["incident:abc"]

    def test_deduped(self):
        records = _citation_records(["incident:abc", "incident:abc"], self.INDEX)
        assert len(records) == 1

    def test_empty_inputs(self):
        assert _citation_records([], self.INDEX) == []
        assert _citation_records(["incident:abc"], {}) == []
