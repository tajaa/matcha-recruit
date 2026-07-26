"""Pure-function tests for Huume's confirm-first safety envelope (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_actions.py -q

Covers `evaluate_huume_action` and `evaluate_plan_step` — modeled on
tests/matcha_work/test_hr_pilot_actions.py for the sibling hr_pilot envelope.
"""

from app.matcha.services.huume.actions import (
    evaluate_huume_action,
    evaluate_plan_step,
    mark_steps_approved,
)

FEATURES_ON = {"huume": True, "matcha_work": True, "offer_letters": True, "employees": True}


def _staged(**overrides):
    base = {"type": "send_offer", "offer_id": "offer-1", "status": "proposed"}
    base.update(overrides)
    return base


class TestEvaluateHuumeAction:
    def test_new_stage_is_stage_kind(self):
        v = evaluate_huume_action(
            staged_action=None, features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=True,
        )
        assert v.kind == "stage"
        assert not v.ok

    def test_nothing_staged_refuses(self):
        v = evaluate_huume_action(
            staged_action=None, features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"

    def test_confirmed_proposal_proceeds(self):
        v = evaluate_huume_action(
            staged_action=_staged(), features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "proceed"
        assert v.ok
        assert v.action["offer_id"] == "offer-1"

    def test_already_sent_status_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(status="sent"), features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"

    def test_unsupported_action_type_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(type="delete_everything"), features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"

    def test_thread_not_in_huume_mode_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(), features=FEATURES_ON, role="client",
            thread_huume_mode=False, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"

    def test_huume_flag_off_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(), features={**FEATURES_ON, "huume": False}, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"

    def test_offer_letters_flag_off_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(), features={**FEATURES_ON, "offer_letters": False}, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"

    def test_employee_role_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(), features=FEATURES_ON, role="employee",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"

    def test_admin_role_proceeds(self):
        v = evaluate_huume_action(
            staged_action=_staged(), features=FEATURES_ON, role="admin",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.ok

    def test_missing_offer_id_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(offer_id=None), features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"


class TestEvaluatePlanStep:
    def _step(self, key="portal_invitation", **overrides):
        base = {"key": key, "status": "proposed", "record_id": None, "reason": None}
        base.update(overrides)
        return base

    def test_already_done_refuses_rerun(self):
        reason = evaluate_plan_step(
            self._step(record_id="emp-1"), features=FEATURES_ON, integrations={}, employee_id="emp-1",
        )
        assert reason == "already done"

    def test_dependent_step_without_employee_waits(self):
        reason = evaluate_plan_step(
            self._step("training_assignment"), features={**FEATURES_ON, "training": True},
            integrations={}, employee_id=None,
        )
        assert reason == "waiting on create_employee to run first"

    def test_create_employee_has_no_employee_dependency(self):
        reason = evaluate_plan_step(
            self._step("create_employee"), features=FEATURES_ON, integrations={}, employee_id=None,
        )
        assert reason is None

    def test_missing_feature_flag_skips(self):
        reason = evaluate_plan_step(
            self._step("training_assignment"), features={**FEATURES_ON, "training": False},
            integrations={}, employee_id="emp-1",
        )
        assert reason is not None and "training" in reason

    def test_google_workspace_requires_connected_integration(self):
        reason = evaluate_plan_step(
            self._step("google_workspace"), features=FEATURES_ON, integrations={}, employee_id="emp-1",
        )
        assert reason is not None and "google" in reason.lower()

    def test_google_workspace_connected_clears(self):
        reason = evaluate_plan_step(
            self._step("google_workspace"), features=FEATURES_ON,
            integrations={"google_workspace": True}, employee_id="emp-1",
        )
        assert reason is None

    def test_jurisdiction_note_always_available(self):
        reason = evaluate_plan_step(
            self._step("jurisdiction_packet_note"), features={}, integrations={}, employee_id="emp-1",
        )
        assert reason is None

    def test_skipped_status_stays_skipped(self):
        reason = evaluate_plan_step(
            self._step("training_assignment", status="skipped", reason="training isn't enabled for this company"),
            features=FEATURES_ON, integrations={}, employee_id="emp-1",
        )
        assert reason == "training isn't enabled for this company"


class TestMarkStepsApproved:
    def _plan(self):
        return {
            "status": "proposed",
            "steps": [
                {"key": "create_employee", "status": "proposed"},
                {"key": "portal_invitation", "status": "proposed"},
                {"key": "training_assignment", "status": "skipped", "reason": "off"},
            ],
        }

    def test_none_approves_all_proposed(self):
        plan = mark_steps_approved(self._plan(), None)
        statuses = {s["key"]: s["status"] for s in plan["steps"]}
        assert statuses["create_employee"] == "approved"
        assert statuses["portal_invitation"] == "approved"
        assert statuses["training_assignment"] == "skipped"  # untouched
        assert plan["status"] == "approved"

    def test_specific_keys_only_approves_named(self):
        plan = mark_steps_approved(self._plan(), ["create_employee"])
        statuses = {s["key"]: s["status"] for s in plan["steps"]}
        assert statuses["create_employee"] == "approved"
        assert statuses["portal_invitation"] == "proposed"

    def test_does_not_mutate_input(self):
        original = self._plan()
        mark_steps_approved(original, None)
        assert original["steps"][0]["status"] == "proposed"
