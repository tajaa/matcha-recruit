"""Pure-function tests for Huume's confirm-first safety envelope (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_actions.py -q

Covers `evaluate_huume_action` and `evaluate_plan_step` — modeled on
tests/matcha_work/test_hr_pilot_actions.py for the sibling hr_pilot envelope.
"""

from app.matcha.services.huume.actions import (
    evaluate_cancel_plan,
    evaluate_huume_action,
    evaluate_plan_execution,
    evaluate_plan_step,
    mark_steps_approved,
    merge_executed_steps,
    resolve_plan_offer_id,
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


class TestEvaluatePlanExecution:
    def test_role_client_with_flags_ok(self):
        assert evaluate_plan_execution(role="client", features=FEATURES_ON) is None

    def test_role_admin_ok(self):
        assert evaluate_plan_execution(role="admin", features=FEATURES_ON) is None

    def test_employee_role_refused(self):
        reason = evaluate_plan_execution(role="employee", features=FEATURES_ON)
        assert reason is not None and "admin" in reason.lower()

    def test_none_role_refused(self):
        assert evaluate_plan_execution(role=None, features=FEATURES_ON) is not None

    def test_huume_flag_off_refused(self):
        reason = evaluate_plan_execution(role="client", features={**FEATURES_ON, "huume": False})
        assert reason is not None and "huume" in reason.lower()

    def test_matcha_work_flag_off_refused(self):
        reason = evaluate_plan_execution(role="client", features={**FEATURES_ON, "matcha_work": False})
        assert reason is not None and "matcha work" in reason.lower()


class TestResolvePlanOfferId:
    def _plans(self, **statuses):
        return {
            oid: {"status": status, "employee": {"first_name": oid}}
            for oid, status in statuses.items()
        }

    def test_explicit_hit(self):
        plans = self._plans(o1="proposed")
        oid, err = resolve_plan_offer_id(plans, "o1", built_this_turn=set())
        assert oid == "o1" and err is None

    def test_explicit_missing_errors(self):
        plans = self._plans(o1="proposed")
        oid, err = resolve_plan_offer_id(plans, "o2", built_this_turn=set())
        assert oid is None
        assert "o2" in err

    def test_explicit_built_this_turn_refused_distinctly(self):
        plans = self._plans(o1="proposed")
        oid, err = resolve_plan_offer_id(plans, "o1", built_this_turn={"o1"})
        assert oid is None
        assert "this turn" in err

    def test_sole_active_resolved_when_omitted(self):
        plans = self._plans(o1="proposed")
        oid, err = resolve_plan_offer_id(plans, None, built_this_turn=set())
        assert oid == "o1" and err is None

    def test_no_active_plans_errors(self):
        plans = self._plans(o1="done")
        oid, err = resolve_plan_offer_id(plans, None, built_this_turn=set())
        assert oid is None
        assert "no onboarding plan" in err.lower()

    def test_ambiguous_multiple_active_lists_candidates(self):
        plans = self._plans(o1="proposed", o2="approved")
        oid, err = resolve_plan_offer_id(plans, None, built_this_turn=set())
        assert oid is None
        assert "o1" in err and "o2" in err

    def test_done_and_failed_plans_are_not_active(self):
        plans = self._plans(o1="done", o2="executing")
        oid, err = resolve_plan_offer_id(plans, None, built_this_turn=set())
        assert oid == "o2" and err is None


class TestEvaluateCancelPlan:
    def test_no_plan_refused(self):
        assert evaluate_cancel_plan(None) is not None

    def test_proposed_allowed(self):
        assert evaluate_cancel_plan({"status": "proposed"}) is None

    def test_approved_allowed(self):
        assert evaluate_cancel_plan({"status": "approved"}) is None

    def test_executing_refused(self):
        assert evaluate_cancel_plan({"status": "executing"}) is not None

    def test_done_refused(self):
        assert evaluate_cancel_plan({"status": "done"}) is not None


class TestMergeExecutedSteps:
    def _base(self, statuses):
        return {
            "status": "executing", "employee_id": "emp-1",
            "steps": [{"key": k, "status": s} for k, s in statuses.items()],
        }

    def test_preserves_concurrent_approval_left_untouched(self):
        base = self._base({"create_employee": "done", "portal_invitation": "approved"})
        executed = self._base({"create_employee": "done", "portal_invitation": "proposed"})
        merged = merge_executed_steps(base, executed)
        by_key = {s["key"]: s["status"] for s in merged["steps"]}
        assert by_key["portal_invitation"] == "approved"

    def test_overlays_done_with_record_id(self):
        base = self._base({"create_employee": "approved"})
        executed = {"status": "executing", "employee_id": "emp-1",
                    "steps": [{"key": "create_employee", "status": "done", "record_id": "emp-1"}]}
        merged = merge_executed_steps(base, executed)
        assert merged["steps"][0]["status"] == "done"
        assert merged["steps"][0]["record_id"] == "emp-1"

    def test_sets_plan_done_when_all_terminal(self):
        base = self._base({"create_employee": "approved"})
        executed = {"status": "executing", "employee_id": "emp-1",
                    "steps": [{"key": "create_employee", "status": "done"}]}
        merged = merge_executed_steps(base, executed)
        assert merged["status"] == "done"

    def test_stays_executing_when_a_step_is_still_approved(self):
        base = self._base({"create_employee": "done", "portal_invitation": "approved"})
        executed = self._base({"create_employee": "done", "portal_invitation": "proposed"})
        merged = merge_executed_steps(base, executed)
        assert merged["status"] == "executing"

    def test_carries_employee_id_from_executed(self):
        base = {"status": "proposed", "employee_id": None, "steps": []}
        executed = {"status": "executing", "employee_id": "emp-9", "steps": []}
        merged = merge_executed_steps(base, executed)
        assert merged["employee_id"] == "emp-9"

    def test_no_base_plan_falls_back_to_executed(self):
        executed = {"status": "executing", "employee_id": "emp-1",
                    "steps": [{"key": "create_employee", "status": "done"}]}
        merged = merge_executed_steps(None, executed)
        assert merged["steps"][0]["status"] == "done"
