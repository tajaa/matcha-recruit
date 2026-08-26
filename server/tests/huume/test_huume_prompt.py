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

    def test_staged_schedule_change_carries_confirm_id(self):
        # Regression: with no dedicated branch, this fell through to the
        # generic "STAGED ACTION: schedule_change." line with NO id shown —
        # the model then guessed the type name AS the confirm_id on the next
        # turn, silently failed the match, and (separately) hallucinated a
        # success message even though nothing executed. Caught live on
        # dev-remote before this branch existed.
        state = {"huume_action": {
            "type": "schedule_change", "kind": "create", "confirm_id": "ab12cd34", "status": "proposed",
        }}
        block = build_state_block(state)
        assert "ab12cd34" in block
        assert "propose_schedule_change" in block

    def test_staged_schedule_batch_names_count_without_none(self):
        state = {"huume_action": {
            "type": "schedule_change", "operation_count": 3,
            "confirm_id": "ab12cd34", "status": "proposed",
        }}
        block = build_state_block(state)
        assert "3 edits" in block
        assert "(None)" not in block

    def test_staged_send_offer_names_recipient_email(self):
        # "Send Maria's latest offer letter" — the admin must be told which
        # address the sign link goes to before they confirm, and the block
        # must carry the re-stage-on-override instruction (recipient_email).
        state = {"huume_action": {
            "type": "send_offer", "offer_id": "offer-1", "candidate_name": "Maria Lopez",
            "recipient_email": "maria@example.com", "status": "proposed",
        }}
        block = build_state_block(state)
        assert "maria@example.com" in block
        assert "Maria Lopez" in block
        assert "recipient_email" in block

    def test_staged_send_offer_without_recipient_email_falls_back(self):
        state = {"huume_action": {
            "type": "send_offer", "offer_id": "offer-1", "status": "proposed",
        }}
        block = build_state_block(state)
        assert "offer-1" in block
        assert "address on file" in block

    def test_huume_offer_pointer_rendered(self):
        state = {"huume_offer": {"offer_id": "offer-2", "status": "accepted"}}
        block = build_state_block(state)
        assert "offer-2" in block and "accepted" in block

    def test_huume_records_pointer_rendered(self):
        state = {"huume_records": [{"record_type": "er_case", "record_id": "rec-1", "label": "ER-2026-002 — Complaint"}]}
        block = build_state_block(state)
        assert "rec-1" in block and "ER-2026-002" in block and "er_case" in block

    def test_huume_records_renders_every_open_record(self):
        state = {"huume_records": [
            {"record_type": "incident", "record_id": "rec-1", "label": "IR-1"},
            {"record_type": "employee", "record_id": "rec-2", "label": "Jane Doe"},
        ]}
        block = build_state_block(state)
        assert "rec-1" in block and "rec-2" in block and "IR-1" in block and "Jane Doe" in block
        assert "(2)" in block

    def test_huume_records_absent_when_not_staged(self):
        block = build_state_block({"huume_offer": {"offer_id": "offer-2", "status": "accepted"}})
        assert "record_id" not in block

    def test_huume_records_empty_list_is_absent(self):
        block = build_state_block({"huume_records": []})
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

    def test_staged_ems_promote_carries_event_id(self):
        state = {
            "huume_action": {
                "type": "ems_promote", "status": "proposed", "event_id": "ev-1",
                "title": "Autoclave failure",
            }
        }
        block = build_state_block(state)
        assert "ev-1" in block
        assert "promote_ems_event" in block
        assert "Autoclave failure" in block

    def test_huume_ir_pointer_rendered(self):
        state = {"huume_ir": {"incident_id": "inc-1", "incident_number": "IR-2026-004"}}
        block = build_state_block(state)
        assert "inc-1" in block and "IR-2026-004" in block
        assert "ask_ir_copilot" in block

    def test_huume_ir_absent_when_not_set(self):
        block = build_state_block({"huume_offer": {"offer_id": "offer-2", "status": "accepted"}})
        assert "incident_id" not in block

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

    def test_lists_promote_ems_event_as_staged(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "promote_ems_event" in prompt

    def test_lists_list_assets_and_send_offer_guidance(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "list_assets" in prompt
        assert "recipient_email" in prompt

    def test_offer_prep_creates_partial_draft_instead_of_questionnaire(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "CREATE THE DRAFT IN THAT TURN" in prompt
        assert "candidate_email and reporting_to" in prompt
        assert "must never block draft creation" in prompt
        assert "set employment_type='Full-Time Exempt'" in prompt

    def test_conversation_contract_prefers_progress_and_human_language(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "capable coworker, not a form or schema validator" in prompt
        assert "take every safe, reversible step" in prompt
        assert "needed only for a later step" in prompt
        assert "Ask one short, natural-language question" in prompt
        assert "Never expose snake_case tool arguments" in prompt
        assert "explain what you already accomplished first" in prompt

    def test_lists_propose_schedule_change_as_staged(self):
        # Previously omitted from the staged-tool list sentence entirely —
        # the model had no prompt guidance that this tool needs a confirm
        # turn like every other staged action.
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "propose_schedule_change" in prompt

    def test_schedule_section_mentions_target_time_hint_and_verbatim_tokens(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "target_time_hint" in prompt
        assert "verbatim" in prompt

    def test_schedule_section_mentions_target_staffing_hint(self):
        # Two shifts sharing date+time+role (one staffed, one open) — the
        # model must reach for this rather than telling the admin to go
        # retime a shift on the Schedule page just to disambiguate.
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "target_staffing_hint" in prompt

    def test_schedule_section_teaches_batch_and_deferred_slot(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-26")
        assert "`changes` array" in prompt
        assert "server preserves the first and defers later attempts" in prompt
