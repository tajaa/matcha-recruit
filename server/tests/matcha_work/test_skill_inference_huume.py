"""_infer_skill_from_state huume_mode filter — a Huume thread with leftover
resume-batch state (candidates/batch_status/...) must infer as if that state
were absent, so a poisoned thread stops rendering the resume panel and stops
prompt-injecting current_skill=resume_batch."""
from app.matcha.services.matcha_work.matcha_work_ai._text import _infer_skill_from_state

RESUME_STATE = {
    "candidates": [{"id": "abc", "name": "X", "status": "analyzed"}],
    "batch_status": "ready",
    "total_count": 1,
    "analyzed_count": 1,
}


def test_default_still_infers_resume_batch():
    assert _infer_skill_from_state(dict(RESUME_STATE)) == "resume_batch"


def test_huume_mode_ignores_resume_batch_state():
    assert _infer_skill_from_state(dict(RESUME_STATE), huume_mode=True) == "chat"


def test_huume_mode_batch_status_alone_not_onboarding():
    # batch_status alone matches the onboarding branch — the filter must drop
    # the whole key set, not just `candidates`.
    assert _infer_skill_from_state({"batch_status": "ready"}, huume_mode=True) == "chat"


def test_huume_mode_preserves_other_skills():
    assert _infer_skill_from_state({"hr_action": {}}, huume_mode=True) == "hr_pilot"
    assert _infer_skill_from_state({**RESUME_STATE, "candidate_name": "Y"}, huume_mode=True) == "offer_letter"


def test_huume_mode_false_is_identity():
    assert _infer_skill_from_state(dict(RESUME_STATE), huume_mode=False) == "resume_batch"


def test_onboarding_employees_key_survives_huume_filter():
    # `employees` is real onboarding state (huume onboarding skill) — only the
    # resume-route keys are filtered.
    assert _infer_skill_from_state({"employees": []}, huume_mode=True) == "onboarding"


def test_input_state_not_mutated():
    s = dict(RESUME_STATE)
    _infer_skill_from_state(s, huume_mode=True)
    assert "candidates" in s
