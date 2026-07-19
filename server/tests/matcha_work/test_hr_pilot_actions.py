"""Pure-function tests for the HR Pilot action safety envelope (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_hr_pilot_actions.py -q

Covers `evaluate_hr_action` — the DB-free half of the envelope. Employee
resolution + the deterministic discipline compliance gate live in the async
executor and are exercised manually against dev (see PR description).
"""

import json
from datetime import date, datetime, timezone

from app.matcha.services.hr_pilot_actions import (
    _parse_iso_dates,
    _slim_compliance_snapshot,
    _validate_discipline_fields,
    _validate_pto_fields,
    _derive_er_title,
    filter_model_staged_hr_action,
    should_stage_handoff,
    evaluate_hr_action,
)

FEATURES_ON = {"hr_pilot": True, "discipline": True}
# Feature set a company with the warm-hand-off subsystems would carry.
FEATURES_ALL = {"hr_pilot": True, "discipline": True, "time_off": True,
                "incidents": True, "er_copilot": True}


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


# --- Blocked (compliance pre-check) proposal ------------------------------

def test_blocked_status_refuses_with_reason():
    v = _evaluate(_proposed(status="blocked",
                            blocked_reason="Barred by CA Lab. Code §246.5(c) — protected leave."))
    assert v.kind == "refuse"
    assert "246.5" in v.message


# --- Warm hand-off actions (ir_report / er_case) --------------------------

def _handoff(atype="er_case", **overrides):
    action = {
        "type": atype,
        "status": "proposed",
        "source": "hard_stop_handoff",
        "narrative": "An employee said a coworker groped her during the closing shift.",
        "category": "harassment_discrimination",
        "escalation_id": "00000000-0000-0000-0000-000000000001",
        "thread_id": "00000000-0000-0000-0000-000000000002",
    }
    action.update(overrides)
    return action


def test_handoff_with_hard_stop_words_proceeds():
    # THE central regression: the sanctioned channel must NOT be refused for
    # carrying the very content that triggered it.
    v = _evaluate(_handoff("er_case"), features=FEATURES_ALL)
    assert v.ok
    assert v.action["type"] == "er_case"
    assert v.action["narrative"].startswith("An employee")


def test_ir_report_handoff_proceeds():
    v = _evaluate(_handoff("ir_report", category="workplace_safety",
                           narrative="A worker fell off a ladder and is bleeding."),
                  features=FEATURES_ALL)
    assert v.ok
    assert v.action["type"] == "ir_report"


def test_handoff_without_source_marker_refuses():
    action = _handoff("er_case")
    action.pop("source")
    v = _evaluate(action, features=FEATURES_ALL)
    assert v.kind == "refuse"


def test_handoff_with_wrong_source_refuses():
    v = _evaluate(_handoff("er_case", source="model"), features=FEATURES_ALL)
    assert v.kind == "refuse"


def test_handoff_missing_subsystem_feature_refuses():
    v = _evaluate(_handoff("er_case"), features={"hr_pilot": True})
    assert v.kind == "refuse"


def test_handoff_empty_narrative_refuses():
    v = _evaluate(_handoff("ir_report", category="workplace_safety", narrative="  "),
                  features=FEATURES_ALL)
    assert v.kind == "refuse"


# --- Model-staging strip guard -------------------------------------------

def test_filter_drops_model_staged_handoff():
    assert filter_model_staged_hr_action({"hr_action": {"type": "er_case"}}) == {}
    assert filter_model_staged_hr_action({"hr_action": {"type": "ir_report"}}) == {}


def test_filter_passes_model_stageable_actions():
    for t in ("discipline_draft", "pto_request"):
        payload = {"hr_action": {"type": t, "status": "proposed"}}
        assert filter_model_staged_hr_action(payload) == payload


# --- should_stage_handoff -------------------------------------------------

def test_should_stage_handoff_maps_categories():
    assert should_stage_handoff(None, "workplace_safety", FEATURES_ALL) == "ir_report"
    assert should_stage_handoff(None, "harassment_discrimination", FEATURES_ALL) == "er_case"


def test_should_stage_handoff_no_target_category():
    assert should_stage_handoff(None, "termination_or_legal", FEATURES_ALL) is None
    assert should_stage_handoff(None, "leave_and_medical", FEATURES_ALL) is None


def test_should_stage_handoff_feature_off():
    assert should_stage_handoff(None, "workplace_safety", {"hr_pilot": True}) is None


def test_should_stage_handoff_suppressed_when_already_staged():
    existing = {"type": "er_case", "status": "proposed"}
    assert should_stage_handoff(existing, "harassment_discrimination", FEATURES_ALL) is None


def test_staged_discipline_does_not_suppress_handoff():
    # Safety outranks a pending write-up — a staged discipline_draft must NOT
    # block a hard-stop hand-off from being staged over it.
    existing = {"type": "discipline_draft", "status": "proposed"}
    assert should_stage_handoff(existing, "workplace_safety", FEATURES_ALL) == "ir_report"


# --- PTO on-behalf --------------------------------------------------------

def _pto(**overrides):
    action = {
        "type": "pto_request",
        "status": "proposed",
        "employee_name": "Jane Doe",
        "request_type": "vacation",
        "start_date": "2026-08-10",
        "end_date": "2026-08-12",
        "hours": 24,
        "reason": "Family trip.",
    }
    action.update(overrides)
    return action


def test_pto_valid_proceeds():
    v = _evaluate(_pto(), features=FEATURES_ALL)
    assert v.ok
    assert v.action["type"] == "pto_request"
    assert v.action["hours"] == 24


def test_pto_sick_type_clarifies():
    v = _evaluate(_pto(request_type="sick"), features=FEATURES_ALL)
    assert v.kind == "clarify"


def test_pto_missing_hours_clarifies():
    v = _evaluate(_pto(hours=None), features=FEATURES_ALL)
    assert v.kind == "clarify"


def test_pto_zero_hours_clarifies():
    v = _evaluate(_pto(hours=0), features=FEATURES_ALL)
    assert v.kind == "clarify"


def test_pto_end_before_start_clarifies():
    v = _evaluate(_pto(start_date="2026-08-12", end_date="2026-08-10"), features=FEATURES_ALL)
    assert v.kind == "clarify"


def test_pto_garbage_dates_clarifies():
    v = _evaluate(_pto(start_date="next week"), features=FEATURES_ALL)
    assert v.kind == "clarify"


def test_pto_missing_time_off_feature_refuses():
    v = _evaluate(_pto(), features={"hr_pilot": True})
    assert v.kind == "refuse"


def test_pto_fmla_in_reason_hard_stops():
    # The hard-stop re-check stays ON for PTO — "out on FMLA" must refuse.
    v = _evaluate(_pto(reason="She's out on FMLA and needs the time counted"), features=FEATURES_ALL)
    assert v.kind == "hard_stop"


# --- Pure field validators + snapshot ------------------------------------

def test_validate_discipline_fields_parity():
    normalized, msg = _validate_discipline_fields(_proposed())
    assert msg is None
    assert normalized["type"] == "discipline_draft"
    assert normalized["occurrence_dates"] == ["2026-07-10", "2026-07-11"]

    _, missing_msg = _validate_discipline_fields(_proposed(employee_name=""))
    assert missing_msg


def test_validate_pto_fields_parity():
    normalized, msg = _validate_pto_fields(_pto())
    assert msg is None
    assert normalized["request_type"] == "vacation"


def test_slim_compliance_snapshot_json_roundtrips_dates():
    verdict = {
        "version": 1,
        "checked_at": datetime.now(timezone.utc),
        "work_state": "CA",
        "state_row": {"statute": "CA Lab. Code §246.5(c)"},
        "blocks": [{"code": "protected_leave_overlap", "detail": "barred",
                    "statute": "CA Lab. Code §246.5(c)", "state": "CA",
                    "dates": [date(2026, 7, 10)]}],
        "advisories": [{"code": "unmapped_state", "detail": "not an all-clear"}],
    }
    slim = _slim_compliance_snapshot(verdict)
    # Must survive json.dumps with NO default (apply_update serializes this way).
    encoded = json.dumps(slim)
    assert "protected_leave_overlap" in encoded
    assert slim["blocks"][0]["statute"] == "CA Lab. Code §246.5(c)"


def test_derive_er_title():
    assert _derive_er_title("Coworker groped her.\nMore detail").startswith("HR Pilot report: Coworker")
    assert _derive_er_title("") == "HR Pilot report"
    long = "x" * 200
    assert len(_derive_er_title(long)) < 120
