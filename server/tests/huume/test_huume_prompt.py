"""Pure-function tests for Huume's staged-state prompt block (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_prompt.py -q

Covers `build_state_block` — the fix for the "model must guess the staged
offer_id on a confirm turn" gap (Huume hardening review #1).
"""

from app.matcha.services.huume.prompt import build_state_block, build_system_prompt


class TestBuildStateBlock:
    def test_empty_state_is_explicit(self):
        block = build_state_block({})
        assert "nothing is currently staged" in block.lower()

    def test_staged_action_carries_offer_id(self):
        state = {"huume_action": {"type": "send_offer", "offer_id": "offer-1", "status": "proposed"}}
        block = build_state_block(state)
        assert "offer-1" in block
        assert "send_offer" in block

    def test_non_proposed_action_omitted(self):
        state = {"huume_action": {"type": "send_offer", "offer_id": "offer-1", "status": "sent"}}
        block = build_state_block(state)
        assert "offer-1" not in block

    def test_huume_offer_pointer_rendered(self):
        state = {"huume_offer": {"offer_id": "offer-2", "status": "accepted"}}
        block = build_state_block(state)
        assert "offer-2" in block and "accepted" in block

    def test_huume_record_pointer_rendered(self):
        state = {"huume_record": {"record_type": "er_case", "record_id": "rec-1", "label": "ER-2026-002 — Complaint"}}
        block = build_state_block(state)
        assert "rec-1" in block and "ER-2026-002" in block and "er case" in block

    def test_huume_record_absent_when_not_staged(self):
        block = build_state_block({"huume_offer": {"offer_id": "offer-2", "status": "accepted"}})
        assert "record_id" not in block

    def test_renders_two_plans_with_step_statuses(self):
        state = {
            "huume_plans": {
                "offer-1": {
                    "status": "proposed",
                    "employee": {"first_name": "Jane", "last_name": "Doe"},
                    "steps": [
                        {"key": "create_employee", "status": "proposed"},
                        {"key": "portal_invitation", "status": "skipped", "reason": "employees isn't enabled"},
                    ],
                },
                "offer-2": {
                    "status": "executing",
                    "employee": {"first_name": "John"},
                    "steps": [{"key": "create_employee", "status": "done"}],
                },
            }
        }
        block = build_state_block(state)
        assert "offer-1" in block and "offer-2" in block
        assert "Jane" in block and "John" in block
        assert "create_employee=proposed" in block
        assert "portal_invitation=skipped (employees isn't enabled)" in block
        assert "create_employee=done" in block

    def test_staged_discipline_draft_carries_confirm_id(self):
        state = {
            "huume_action": {
                "type": "discipline_draft", "status": "proposed", "confirm_id": "ab12cd34",
                "employee_name": "Jane Doe", "infraction_type": "attendance",
            }
        }
        block = build_state_block(state)
        assert "ab12cd34" in block
        assert "Jane Doe" in block
        assert "draft_discipline" in block

    def test_all_present_but_terminal_is_still_nothing_staged(self):
        state = {
            "huume_action": {"type": "send_offer", "offer_id": "x", "status": "sent"},
            "huume_plans": {},
        }
        block = build_state_block(state)
        assert "nothing is currently staged" in block.lower()


class TestBuildSystemPrompt:
    def test_embeds_state_block(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26", state_block="STAGED_MARKER_XYZ")
        assert "STAGED_MARKER_XYZ" in prompt

    def test_defaults_to_nothing_staged_when_block_omitted(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "Nothing is currently staged" in prompt

    def test_lists_cancel_staged_tool(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "cancel_staged" in prompt
