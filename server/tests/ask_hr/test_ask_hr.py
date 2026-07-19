"""Employee Ask HR — pure-function tests (no DB, no Gemini).

The two things that must not regress: sensitive questions never reach a model,
and answers can only cite records that exist.
"""

import pytest

from app.matcha.services import ask_hr as svc
from app.matcha.services.hr_pilot_escalation import classify_message
from app.matcha.services.legal_defense import validate_citations


# --------------------------------------------------------------------------- #
# The hard stop — the whole safety story for this feature.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("question,category", [
    ("My supervisor keeps making comments about my body and it won't stop",
     "harassment_discrimination"),
    ("I slipped on the wet floor in the back and hurt my wrist during my shift",
     "workplace_safety"),
    ("I need to take FMLA leave for surgery next month", "leave_and_medical"),
    ("Can they fire me for this? I'm thinking about talking to a lawyer",
     "termination_or_legal"),
])
def test_sensitive_questions_are_refused(question, category):
    verdict = svc.should_refuse(question)
    assert verdict.hard_stop is True
    assert verdict.category == category


@pytest.mark.parametrize("question", [
    "How many vacation days do I get per year?",
    "What time does the shift differential start?",
    "Where do I find the dress code policy?",
    "How do I swap a shift with a coworker?",
])
def test_ordinary_questions_are_not_refused(question):
    assert svc.should_refuse(question).hard_stop is False


def test_empty_question_is_not_refused():
    assert svc.should_refuse("").hard_stop is False
    assert svc.should_refuse(None).hard_stop is False


def test_refusal_message_does_not_echo_the_question():
    """The refusal is persisted and may be read over the employee's shoulder —
    it must not repeat what they disclosed."""
    question = "my supervisor groped me at the holiday party"
    verdict = svc.should_refuse(question)
    msg = svc.refusal_message(verdict)
    # None of the disclosure's own words come back. ("manager" DOES appear, in
    # the reassurance that nothing was shared with theirs — that is the point of
    # the sentence, not an echo.)
    for word in ("groped", "supervisor", "holiday", "party"):
        assert word not in msg.lower()


def test_refusal_message_discloses_that_hr_was_notified():
    """Filing on the employee's behalf without telling them would be a surprise
    at exactly the moment trust matters most."""
    msg = svc.refusal_message(svc.should_refuse("I want to report harassment"))
    assert "HR team" in msg
    assert "follow up" in msg.lower()


def test_refusal_message_promises_no_manager_disclosure():
    msg = svc.refusal_message(svc.should_refuse("I want to report harassment")).lower()
    assert "manager" in msg
    assert "nothing you wrote has been shared" in msg


@pytest.mark.parametrize("question,category", [
    # The gap that shipped: employee first-person phrasing naming no legal term.
    ("he keeps touching me and I've asked him to stop", "harassment_discrimination"),
    ("someone made me feel uncomfortable in the break room", "harassment_discrimination"),
    ("I got hurt moving a pallet yesterday", "workplace_safety"),
    ("I tripped over a cord in the hallway", "workplace_safety"),
    ("I slipped on the wet floor and hurt my wrist", "workplace_safety"),
    ("the ladder in the stockroom is unsafe", "workplace_safety"),
    ("I burned my hand on the fryer", "workplace_safety"),
    ("I have surgery scheduled and need time off", "leave_and_medical"),
])
def test_first_person_phrasing_is_caught(question, category):
    """These matched nothing before the employee surface existed — the patterns
    were written in supervisor vocabulary. See the module docstring."""
    verdict = svc.should_refuse(question)
    assert verdict.hard_stop is True
    assert verdict.category == category


@pytest.mark.parametrize("question", [
    # Core supervisor questions that share vocabulary with the first-person
    # injury/harassment patterns. If the employee-only overlay ever leaks back
    # into the shared set, HR Pilot starts hard-stopping its own core use cases.
    "an employee fell behind on their targets this quarter",
    "the team is burned out and morale is low",
    "how do I address inappropriate clothing under the dress code?",
    "an employee threatened to quit over their schedule",
])
def test_employee_overlay_does_not_leak_to_supervisor(question):
    assert classify_message(question).hard_stop is False, (
        "employee-only pattern leaked into the shared supervisor set"
    )


@pytest.mark.parametrize("question", [
    "I slipped on the wet floor and hurt my wrist",
    "he keeps touching me and I've asked him to stop",
])
def test_same_text_differs_by_surface(question):
    """The whole point of the split: identical text, different verdict, because
    the reader is different."""
    assert svc.should_refuse(question).hard_stop is True
    assert classify_message(question).hard_stop is False


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #

@pytest.fixture
def corpus():
    return {
        "sources": {
            "existing_policies": {
                "label": "Existing policies",
                "records": [{"cid": "policy:abc", "ref": "PTO Policy",
                             "summary": "15 days accrued annually.", "when": "current"}],
            },
            "empty_group": {"label": "Nothing here", "records": []},
        },
        "index": {"policy:abc": {"cid": "policy:abc", "ref": "PTO Policy",
                                 "summary": "15 days accrued annually."}},
        "notes": [],
    }


def test_prompt_includes_corpus_records(corpus):
    prompt = svc.build_prompt({}, [], corpus, "How much PTO do I get?")
    assert "[policy:abc]" in prompt
    assert "15 days accrued annually." in prompt
    assert "How much PTO do I get?" in prompt


def test_prompt_omits_empty_source_groups(corpus):
    assert "Nothing here" not in svc.build_prompt({}, [], corpus, "hi")


def test_prompt_carries_the_askers_own_context(corpus):
    prompt = svc.build_prompt(
        {"job_title": "Line Cook", "work_state": "CA"}, [], corpus, "hi")
    assert "Line Cook" in prompt
    assert "CA" in prompt


def test_prompt_handles_employee_with_nothing_on_file(corpus):
    prompt = svc.build_prompt({}, [], corpus, "hi")
    assert "(not on file)" in prompt


def test_prompt_says_employee_not_manager(corpus):
    """The voice split from HR Pilot is the point of a separate prompt — if this
    drifts back to coaching language the feature is answering the wrong person."""
    prompt = svc.build_prompt({}, [], corpus, "hi")
    assert "EMPLOYEE" in prompt
    assert "Not a manager" in prompt


def test_prompt_forbids_inventing_policy(corpus):
    prompt = svc.build_prompt({}, [], corpus, "hi")
    assert "NEVER invent" in prompt
    assert "not legal advice" in prompt.lower() or "NOT giving legal advice" in prompt


def test_empty_corpus_is_stated_not_silently_empty(corpus):
    prompt = svc.build_prompt({}, [], {"sources": {}, "index": {}}, "hi")
    assert "no handbook or policy material on file" in prompt


def test_history_is_windowed(corpus):
    history = [{"role": "user", "content": f"msg{i}"} for i in range(30)]
    prompt = svc.build_prompt({}, history, corpus, "latest")
    assert "msg29" in prompt
    assert "msg0" not in prompt


def test_history_ignores_non_conversational_roles(corpus):
    history = [{"role": "system", "content": "SECRET"}, {"role": "user", "content": "hi"}]
    assert "SECRET" not in svc.build_prompt({}, history, corpus, "q")


# --------------------------------------------------------------------------- #
# The citation gate, over the Ask HR corpus shape
# --------------------------------------------------------------------------- #

def test_gate_keeps_real_ids_and_drops_invented(corpus):
    clean, dropped = validate_citations(
        [{"point": "You accrue 15 days.", "cited_ids": ["policy:abc", "policy:nope"]}],
        corpus["index"],
    )
    assert clean[0]["cited_ids"] == ["policy:abc"]
    assert dropped == ["policy:nope"]


def test_gate_survives_a_model_returning_junk(corpus):
    clean, dropped = validate_citations(
        ["not a dict", {"point": "x", "cited_ids": "not-a-list"}, {}], corpus["index"]
    )
    assert all(c["cited_ids"] == [] for c in clean)
    assert dropped == []
