"""Pure editor-surface scheduling chat coverage."""

from datetime import date

from app.matcha.services.scheduling.schedule_chat import (
    _coerce_template_request,
    _parse_schedule_json,
    template_proposal_text,
    template_result_text,
)
from app.matcha.services.scheduling.schedule_chat_rules import resolve_week


def test_editor_week_override_anchors_this_and_next_week():
    open_week = date(2026, 8, 16)
    assert resolve_week(None, date(2026, 8, 17), open_week) == open_week
    assert resolve_week("next_week", date(2026, 8, 17), open_week) == date(2026, 8, 23)


def test_template_parse_is_actionable_and_coerced():
    parsed = _parse_schedule_json(
        '{"actionable":true,"action":"template","ack":"Save it",'
        '"template_request":{"name":"Opener","role":"Front Desk",'
        '"start_time":"06:00","end_time":"14:00",'
        '"weekdays":["Monday","Fri"],"count":2}}'
    )
    assert parsed["action"] == "template"
    assert parsed["actionable"] is True
    assert parsed["template_request"]["count"] == 2
    assert parsed["template_request"]["weekdays"] == ["monday", "fri"]


def test_template_request_requires_a_name_and_clamps_headcount():
    assert _coerce_template_request({"start_time": "06:00"}) is None
    request = _coerce_template_request({"name": "Opener", "count": 999})
    assert request["count"] == 99


def test_template_text_is_deterministic():
    template = {
        "name": "Opener", "start_time": "06:00", "end_time": "14:00",
        "required_staff": 2, "days_of_week": [1, 5],
    }
    proposal = {"template": template}
    assert "Opener" in template_proposal_text(proposal)
    assert template_result_text(template) == "Created template **Opener**."
