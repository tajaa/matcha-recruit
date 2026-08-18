"""Pure editor-surface scheduling chat coverage."""

from datetime import date

from app.matcha.services.scheduling.schedule_chat import (
    _coerce_apply_request,
    _coerce_template_request,
    _parse_schedule_json,
    apply_template_proposal_text,
    template_proposal_text,
    template_result_text,
)
from app.matcha.services.scheduling.schedule_chat_rules import resolve_week


def test_editor_week_override_anchors_this_and_next_week():
    open_week = date(2026, 8, 16)
    assert resolve_week(None, date(2026, 8, 17), open_week) == open_week
    assert resolve_week("next_week", date(2026, 8, 17), open_week) == date(2026, 8, 23)


def test_template_parse_yields_blocks():
    # "Standard Week: box office 9-10 Mon-Fri, weekend crew 9-11 Sat-Sun" —
    # a week template with two blocks.
    parsed = _parse_schedule_json(
        '{"actionable":true,"action":"template","ack":"Save it",'
        '"template_request":{"name":"Standard Week",'
        '"blocks":[{"name":"Box Office","start_time":"09:00","end_time":"22:00",'
        '"weekdays":["Monday","Tuesday","Wednesday","Thursday","Friday"],"count":3},'
        '{"name":"Weekend Crew","start_time":"09:00","end_time":"23:00",'
        '"weekdays":["Saturday","Sunday"],"count":5}]}}'
    )
    assert parsed["action"] == "template"
    assert parsed["actionable"] is True
    assert len(parsed["template_request"]["blocks"]) == 2
    assert parsed["template_request"]["blocks"][0]["name"] == "Box Office"


def test_template_parse_wraps_legacy_flat_shape():
    # The pre-week model output (start_time/weekdays at the top level, no
    # "blocks" key) becomes exactly one block named after the week — this is
    # the one-liner path ("save a closer template, 5pm to 11pm weekdays").
    parsed = _parse_schedule_json(
        '{"actionable":true,"action":"template","ack":"Save it",'
        '"template_request":{"name":"Closer","role":"Front Desk",'
        '"start_time":"17:00","end_time":"23:00",'
        '"weekdays":["Monday","Fri"],"count":2}}'
    )
    blocks = parsed["template_request"]["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["name"] == "Closer"
    assert blocks[0]["count"] == 2
    assert blocks[0]["weekdays"] == ["monday", "fri"]


def test_template_request_requires_a_name():
    assert _coerce_template_request({"blocks": [{"name": "B", "start_time": "06:00"}]}) is None


def test_template_block_survives_missing_times():
    # Under-specified blocks must reach build_template_proposal so it can
    # clarify per block; dropping them here would silently lose a block.
    request = _coerce_template_request({
        "name": "Standard Week", "blocks": [{"name": "Box Office"}],
    })
    assert len(request["blocks"]) == 1
    assert request["blocks"][0]["start_time"] is None


def test_template_request_caps_block_count():
    request = _coerce_template_request({
        "name": "Silly",
        "blocks": [{"name": f"B{i}", "start_time": "09:00", "end_time": "17:00",
                    "weekdays": ["monday"]} for i in range(20)],
    })
    assert len(request["blocks"]) == 12


def test_apply_request_coercion():
    request = _coerce_apply_request({"template_hint": "Standard Week", "weeks": 999})
    assert request["weeks"] == 8
    bad_date = _coerce_apply_request({"template_hint": "Standard Week", "start_date": "not-a-date"})
    assert bad_date["start_date"] is None


def test_apply_request_requires_a_template_hint():
    assert _coerce_apply_request({"weeks": 2}) is None


def test_template_proposal_text_lists_blocks():
    proposal = {"week_template": {
        "name": "Standard Week",
        "blocks": [
            {"name": "Box Office", "start_time": "09:00", "end_time": "22:00",
             "required_staff": 3, "days_of_week": [1, 2, 3, 4, 5]},
            {"name": "Weekend Crew", "start_time": "09:00", "end_time": "23:00",
             "required_staff": 5, "days_of_week": [0, 6]},
        ],
    }}
    text = template_proposal_text(proposal)
    assert "Standard Week" in text and "Box Office" in text and "Weekend Crew" in text


def test_template_result_text_counts_blocks():
    week_template = {"name": "Standard Week", "blocks": [{}, {}]}
    assert template_result_text(week_template) == "Created week template **Standard Week** with 2 block(s)."


def test_apply_template_proposal_text_is_deterministic():
    proposal = {
        "week_template_name": "Standard Week", "start_date": "2026-07-12", "end_date": "2026-07-18",
        "total_shifts": 7,
        "blocks_preview": [{"name": "Box Office", "start_time": "09:00", "end_time": "22:00", "shifts": 5}],
    }
    text = apply_template_proposal_text(proposal)
    assert "Standard Week" in text and "7 shifts" in text and "Box Office" in text
