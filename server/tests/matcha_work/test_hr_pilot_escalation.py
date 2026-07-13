"""Pure-function tests for the HR Pilot hard-stop gate (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_hr_pilot_escalation.py -q
"""

from app.matcha.services.hr_pilot_escalation import (
    CORPORATE_HR_ESCALATION_NOTICE,
    classify_message,
)


def test_harassment_hard_stop():
    v = classify_message("He's been sexually harassing a coworker for weeks")
    assert v.hard_stop is True
    assert v.category == "harassment_discrimination"
    assert v.notice


def test_workplace_safety_hard_stop():
    v = classify_message("An employee fell off the ladder and is bleeding")
    assert v.hard_stop is True
    assert v.category == "workplace_safety"


def test_leave_and_medical_hard_stop():
    v = classify_message("She's asking about FMLA for a pregnancy")
    assert v.hard_stop is True
    assert v.category == "leave_and_medical"


def test_termination_or_legal_hard_stop():
    v = classify_message("I want to fire him today, can I do that?")
    assert v.hard_stop is True
    assert v.category == "termination_or_legal"


def test_benign_message_passes():
    v = classify_message("Can I schedule someone for a double shift on Saturday?")
    assert v.hard_stop is False
    assert v.category is None
    assert v.notice is None


def test_empty_message_passes():
    assert classify_message("").hard_stop is False
    assert classify_message("   ").hard_stop is False


def test_first_match_wins_most_severe_category():
    # Trips both harassment and termination keywords — harassment (more
    # severe, ordered first in the registry) must win.
    v = classify_message("I want to fire him for the harassment complaint")
    assert v.hard_stop is True
    assert v.category == "harassment_discrimination"


def test_notice_falls_back_to_generic_when_unset():
    v = classify_message("workers comp claim filed")
    assert v.hard_stop is True
    # Every real category sets its own notice; the module-level generic
    # fallback exists for callers that don't trust verdict.notice.
    assert v.notice != CORPORATE_HR_ESCALATION_NOTICE
    assert CORPORATE_HR_ESCALATION_NOTICE
