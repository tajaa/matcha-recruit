"""Pure-function tests for the HR Pilot action safety envelope (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_hr_pilot_actions.py -q

Covers `evaluate_hr_action` — the DB-free half of the envelope. Employee
resolution + the deterministic discipline compliance gate live in the async
executor and are exercised manually against dev (see PR description).
"""

from datetime import date

from app.matcha.services.hr_pilot_actions import (
    _parse_iso_dates,
    evaluate_hr_action,
)

FEATURES_ON = {"hr_pilot": True, "discipline": True}


def _proposed(**overrides):
    action = {
        "type": "discipline_draft",
        "status": "proposed",
        "employee_name": "Jane Doe",
        "infraction_type": "attendance",
        "severity": "moderate",
        "occurrence_dates": ["2026-07-10", "2026-07-11"],
        "description": "No-call no-show on two scheduled shifts.",
        "expected_improvement": "Call in at least one hour before shift.",
    }
    action.update(overrides)
    return action


def _evaluate(staged, **kw):
    params = dict(
        staged_action=staged,
        features=FEATURES_ON,
        role="client",
        thread_hr_pilot_mode=True,
        this_turn_has_new_action=False,
    )
    params.update(kw)
    return evaluate_hr_action(**params)


# --- Date parsing ---------------------------------------------------------

def test_parse_iso_dates_valid():
    parsed, invalid = _parse_iso_dates(["2026-07-10", "2026-01-02"])
    assert parsed == [date(2026, 7, 10), date(2026, 1, 2)]
    assert invalid == []


def test_parse_iso_dates_rejects_garbage():
    parsed, invalid = _parse_iso_dates(["last tuesday", "2026-13-40", ""])
    assert parsed == []
    assert len(invalid) == 3


def test_parse_iso_dates_non_list():
    parsed, invalid = _parse_iso_dates("2026-07-10")
    assert parsed == []
    assert invalid


# --- Happy path -----------------------------------------------------------

def test_valid_proposal_proceeds():
    v = _evaluate(_proposed())
    assert v.ok
    assert v.action["type"] == "discipline_draft"
    assert v.action["occurrence_dates"] == ["2026-07-10", "2026-07-11"]


# --- Confirm-first (two-turn) --------------------------------------------

def test_same_turn_stage_and_execute_is_staged_only():
    v = _evaluate(_proposed(), this_turn_has_new_action=True)
    assert not v.ok
    assert v.kind == "stage"


def test_nothing_staged_refuses():
    v = _evaluate(None)
    assert v.kind == "refuse"


def test_already_executed_refuses():
    v = _evaluate(_proposed(status="executed"))
    assert v.kind == "refuse"


# --- Authorization --------------------------------------------------------

def test_not_hr_pilot_thread_refuses():
    v = _evaluate(_proposed(), thread_hr_pilot_mode=False)
    assert v.kind == "refuse"


def test_missing_hr_pilot_feature_refuses():
    v = _evaluate(_proposed(), features={"discipline": True})
    assert v.kind == "refuse"


def test_missing_subsystem_feature_refuses():
    v = _evaluate(_proposed(), features={"hr_pilot": True})
    assert v.kind == "refuse"


def test_non_admin_role_refuses():
    v = _evaluate(_proposed(), role="employee")
    assert v.kind == "refuse"


# --- Field validation -----------------------------------------------------

def test_sensitive_infraction_type_clarifies():
    v = _evaluate(_proposed(infraction_type="harassment"))
    assert v.kind == "clarify"


def test_missing_employee_clarifies():
    v = _evaluate(_proposed(employee_name="  "))
    assert v.kind == "clarify"


def test_no_dates_clarifies():
    v = _evaluate(_proposed(occurrence_dates=[]))
    assert v.kind == "clarify"


def test_unparseable_dates_clarifies():
    v = _evaluate(_proposed(occurrence_dates=["yesterday"]))
    assert v.kind == "clarify"


def test_invalid_severity_clarifies():
    v = _evaluate(_proposed(severity="catastrophic"))
    assert v.kind == "clarify"


def test_missing_description_clarifies():
    v = _evaluate(_proposed(description=""))
    assert v.kind == "clarify"


# --- Content safety (hard-stop re-check on the action payload) ------------

def test_hard_stop_text_in_action_is_refused_and_escalated():
    # Even with a permitted infraction_type, sensitive wording in the free-text
    # description trips the deterministic gate.
    v = _evaluate(_proposed(description="He keeps sexually harassing the new hire on shift."))
    assert v.kind == "hard_stop"
    assert v.escalate is True
    assert v.category == "harassment_discrimination"
