"""compose_clarify_followup must carry every prior clarify round forward,
not just the current one — dropping earlier rounds meant a second-round
answer (e.g. hours) fed Stage A a re-parse with no memory of the first
round's already-answered question (e.g. location), so it got re-asked.
Pure — no DB, no Gemini.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_clarify_followup.py -q
"""

from app.matcha.services.scheduling.schedule_chat import compose_clarify_followup


def test_first_round_has_no_history():
    proposal = {
        "original_content": "I need two openers tomorrow",
        "clarify_question": "Which location did you mean?",
        "clarify_history": [],
    }
    out = compose_clarify_followup(proposal, "wilshire")
    assert out == (
        "I need two openers tomorrow\n"
        "(Q: Which location did you mean? A: wilshire)"
    )


def test_second_round_carries_first_round_forward():
    proposal = {
        "original_content": "I need two openers tomorrow",
        "clarify_question": "What hours should the opener run?",
        "clarify_history": [
            {"q": "Which location did you mean?", "a": "wilshire"},
        ],
    }
    out = compose_clarify_followup(proposal, "8am to 4pm")
    assert out == (
        "I need two openers tomorrow\n"
        "(Q: Which location did you mean? A: wilshire)\n"
        "(Q: What hours should the opener run? A: 8am to 4pm)"
    )


def test_missing_history_key_treated_as_empty():
    proposal = {"original_content": "book a closer", "clarify_question": "Which location?"}
    out = compose_clarify_followup(proposal, "la jolla")
    assert out == "book a closer\n(Q: Which location? A: la jolla)"
