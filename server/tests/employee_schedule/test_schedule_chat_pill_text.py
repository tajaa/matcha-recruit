"""proposal_text's honesty line — must read the pre-computed
`proposal['rules_unmapped']` flag (set once in `build_proposal` from
`shift_compliance._approved_db_rules`), never re-derive via
`schedule_compliance.rules_summary(state)` with no `db_rules` arg, which
always reports "unmapped" for a non-curated state even when an approved
catalog extraction evaluated every shift. Pure — no DB, no Gemini.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_pill_text.py -q
"""

from app.matcha.services.scheduling.schedule_chat import proposal_text

_BASE_PROPOSAL = {
    "ack": "Got it.",
    "week_start": "2026-08-02",
    "location": {"name": "La Jolla Studio", "city": "San Diego", "state": "CA"},
    "shifts": [
        {
            "label": "opener", "starts_at": "2026-08-03T06:00:00+00:00",
            "ends_at": "2026-08-03T14:00:00+00:00", "required_staff": 1,
            "open_slots": 0, "assignees": [], "intrinsic_violations": [], "excluded": [],
        },
    ],
}


def test_honesty_line_omitted_when_rules_are_mapped():
    proposal = {**_BASE_PROPOSAL, "rules_unmapped": False}
    text = proposal_text(proposal, "TX")
    assert "don't have codified scheduling thresholds" not in text


def test_honesty_line_present_when_rules_unmapped():
    proposal = {**_BASE_PROPOSAL, "rules_unmapped": True}
    text = proposal_text(proposal, "TX")
    assert "don't have codified scheduling thresholds for TX" in text


def test_honesty_line_omitted_when_state_is_none():
    proposal = {**_BASE_PROPOSAL, "rules_unmapped": True}
    text = proposal_text(proposal, None)
    assert "don't have codified scheduling thresholds" not in text
