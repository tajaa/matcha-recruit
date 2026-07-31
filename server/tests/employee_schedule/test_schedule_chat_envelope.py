"""Pure-function tests for evaluate_schedule_proposal (no DB/Gemini) — the
@huume channel-scheduling safety envelope. Modeled on
tests/ems/test_promote_envelope.py for the sibling EMS envelope.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_envelope.py -q
"""

import pytest

from app.matcha.services.scheduling.schedule_chat_rules import evaluate_schedule_proposal

FEATURES_ON = {"ems": True, "employee_schedule": True, "matcha_work": True}


class TestRoleGate:
    def test_client_proceeds(self):
        v = evaluate_schedule_proposal(role="client", features=FEATURES_ON, stage="propose")
        assert v.ok

    def test_admin_proceeds(self):
        v = evaluate_schedule_proposal(role="admin", features=FEATURES_ON, stage="propose")
        assert v.ok

    @pytest.mark.parametrize("role", ["employee", "candidate", "individual", "broker", None])
    def test_other_roles_refuse_with_portal_pointer(self, role):
        v = evaluate_schedule_proposal(role=role, features=FEATURES_ON, stage="propose")
        assert v.kind == "refuse"
        assert "portal" in v.reason.lower()


class TestFeatureGate:
    def test_ems_off_refuses(self):
        features = {**FEATURES_ON, "ems": False}
        v = evaluate_schedule_proposal(role="admin", features=features, stage="propose")
        assert v.kind == "refuse"

    def test_employee_schedule_off_refuses_with_specific_text(self):
        features = {**FEATURES_ON, "employee_schedule": False}
        v = evaluate_schedule_proposal(role="admin", features=features, stage="propose")
        assert v.kind == "refuse"
        assert "Scheduling isn't turned on" in v.reason

    def test_missing_flags_default_off(self):
        v = evaluate_schedule_proposal(role="admin", features={}, stage="propose")
        assert v.kind == "refuse"


class TestConfirmStage:
    @pytest.mark.parametrize("status", ["confirmed", "cancelled", "expired"])
    def test_terminal_status_refuses(self, status):
        v = evaluate_schedule_proposal(
            role="admin", features=FEATURES_ON, stage="confirm", proposal_status=status,
        )
        assert v.kind == "refuse"
        assert status in v.reason

    @pytest.mark.parametrize("status", ["proposed", "clarifying"])
    def test_live_status_proceeds(self, status):
        v = evaluate_schedule_proposal(
            role="client", features=FEATURES_ON, stage="confirm", proposal_status=status,
        )
        assert v.ok

    def test_role_gate_runs_before_status_check(self):
        # An employee replying to a manager's confirmed proposal should get
        # the role message, not a status message — role is checked first.
        v = evaluate_schedule_proposal(
            role="employee", features=FEATURES_ON, stage="confirm", proposal_status="confirmed",
        )
        assert "portal" in v.reason.lower()


class TestProposeStageIgnoresStatus:
    def test_propose_stage_ok_with_no_status(self):
        v = evaluate_schedule_proposal(role="admin", features=FEATURES_ON, stage="propose")
        assert v.ok

    def test_propose_stage_ignores_a_stray_status_value(self):
        v = evaluate_schedule_proposal(
            role="admin", features=FEATURES_ON, stage="propose", proposal_status="confirmed",
        )
        assert v.ok
