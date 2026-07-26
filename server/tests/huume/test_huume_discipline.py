"""Pure-function tests for the discipline-draft staged action (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_discipline.py -q

Covers `evaluate_huume_action`'s discipline_draft branch: authz-before-stage
ordering (shared with send_offer), field validation via the shared
(now-public) `validate_discipline_fields`, and the hard-stop re-check via
`classify_message`. Mirrors `test_huume_actions.py`'s send_offer coverage.
"""

from app.matcha.services.huume.actions import evaluate_huume_action
from app.matcha.services.huume.tools import TOOLS_BY_NAME

FEATURES_ON = {"huume": True, "matcha_work": True, "discipline": True}


def _staged(**overrides):
    base = {
        "type": "discipline_draft",
        "status": "proposed",
        "confirm_id": "abcd1234",
        "employee_name": "Jane Doe",
        "infraction_type": "attendance",
        "severity": "moderate",
        "occurrence_dates": ["2026-07-01"],
        "description": "Arrived over an hour late three times this week.",
        "expected_improvement": None,
    }
    base.update(overrides)
    return base


class TestEvaluateHuumeActionDiscipline:
    def test_new_stage_is_stage_kind(self):
        v = evaluate_huume_action(
            staged_action=_staged(), features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=True,
        )
        assert v.kind == "stage"
        assert not v.ok

    def test_missing_discipline_flag_refuses_before_stage(self):
        # Authz runs BEFORE the stage branch — a caller who will ultimately
        # fail the flag gate is refused immediately, not told "reply confirm".
        v = evaluate_huume_action(
            staged_action=_staged(), features={**FEATURES_ON, "discipline": False}, role="client",
            thread_huume_mode=True, this_turn_staged_new=True,
        )
        assert v.kind == "refuse"
        assert "discipline" in v.message

    def test_wrong_role_refuses_before_stage(self):
        v = evaluate_huume_action(
            staged_action=_staged(), features=FEATURES_ON, role="employee",
            thread_huume_mode=True, this_turn_staged_new=True,
        )
        assert v.kind == "refuse"

    def test_confirmed_valid_proposal_proceeds(self):
        v = evaluate_huume_action(
            staged_action=_staged(), features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.ok
        assert v.action["employee_name"] == "Jane Doe"
        assert v.action["occurrence_dates"] == ["2026-07-01"]

    def test_confirm_missing_occurrence_dates_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(occurrence_dates=[]), features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"
        assert "date" in v.message.lower()

    def test_confirm_invalid_infraction_type_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(infraction_type="harassment"), features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"
        assert "corporate HR" in v.message

    def test_confirm_hard_stop_text_refuses(self):
        # classify_message defaults to the SUPERVISOR pattern set (this is a
        # supervisor-facing tool) — use supervisor-vocabulary phrasing, not
        # first-person employee phrasing (a separate, employee-only overlay).
        v = evaluate_huume_action(
            staged_action=_staged(description="This is a harassment complaint from a coworker."),
            features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"

    def test_status_not_proposed_refuses(self):
        v = evaluate_huume_action(
            staged_action=_staged(status="filed"), features=FEATURES_ON, role="client",
            thread_huume_mode=True, this_turn_staged_new=False,
        )
        assert v.kind == "refuse"


class TestDraftDisciplineToolRegistered:
    def test_tool_is_staged_kind(self):
        assert TOOLS_BY_NAME["draft_discipline"].kind == "staged"

    def test_required_fields(self):
        required = set(TOOLS_BY_NAME["draft_discipline"].declaration.parameters.required)
        assert required == {"employee_name", "infraction_type", "occurrence_dates", "description"}
