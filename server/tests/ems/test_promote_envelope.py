"""Pure-function tests for evaluate_promote (no DB/Gemini) — the EMS
event->incident promotion safety envelope. Modeled on
tests/huume/test_huume_actions.py for the sibling huume envelope.

    cd server && ./venv/bin/python -m pytest tests/ems/test_promote_envelope.py -q
"""

from app.matcha.services.ems.promote import evaluate_promote

FEATURES_ON = {"ems": True, "incidents": True, "matcha_work": True}


class TestEvaluatePromote:
    def test_client_with_both_flags_and_logged_status_proceeds(self):
        v = evaluate_promote(role="client", features=FEATURES_ON, event_status="logged")
        assert v.kind == "proceed"
        assert v.ok

    def test_admin_with_both_flags_and_logged_status_proceeds(self):
        v = evaluate_promote(role="admin", features=FEATURES_ON, event_status="logged")
        assert v.ok

    def test_employee_role_refuses(self):
        v = evaluate_promote(role="employee", features=FEATURES_ON, event_status="logged")
        assert v.kind == "refuse"
        assert v.http_status == 403

    def test_individual_role_refuses(self):
        v = evaluate_promote(role="individual", features=FEATURES_ON, event_status="logged")
        assert v.kind == "refuse"
        assert v.http_status == 403

    def test_none_role_refuses(self):
        v = evaluate_promote(role=None, features=FEATURES_ON, event_status="logged")
        assert v.kind == "refuse"

    def test_refuses_without_ems_flag(self):
        features = {**FEATURES_ON, "ems": False}
        v = evaluate_promote(role="client", features=features, event_status="logged")
        assert v.kind == "refuse"
        assert v.http_status == 403

    def test_refuses_without_incidents_flag(self):
        features = {**FEATURES_ON, "incidents": False}
        v = evaluate_promote(role="client", features=features, event_status="logged")
        assert v.kind == "refuse"
        assert v.http_status == 403

    def test_refuses_already_promoted_status(self):
        v = evaluate_promote(role="client", features=FEATURES_ON, event_status="promoted")
        assert v.kind == "refuse"
        assert v.http_status == 409

    def test_refuses_dismissed_status(self):
        v = evaluate_promote(role="client", features=FEATURES_ON, event_status="dismissed")
        assert v.kind == "refuse"
        assert v.http_status == 409
