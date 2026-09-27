"""Config materialization (services/sym_chat/kinds.py)."""
from datetime import date

import pytest

from app.matcha.services.sym_chat.kinds import materialize_config, parse_hhmm, stance_template

TODAY = date(2030, 1, 1)


def test_schedule_defaults_and_normalisation():
    cfg = materialize_config("schedule", {"date": "2030-01-02", "bogus": 1}, today=TODAY)
    assert cfg == {
        "date": "2030-01-02", "window_start": "09:00", "window_end": "17:00",
        "duration_min": 30, "step_min": 15, "timezone": "America/Los_Angeles",
    }


@pytest.mark.parametrize("raw, message", [
    ({}, "date is required"),
    ({"date": "01/02/2030"}, "YYYY-MM-DD"),
    ({"date": "2029-12-31"}, "in the past"),
    ({"date": "2030-01-02", "timezone": "Mars/Base"}, "Unknown timezone"),
    ({"date": "2030-01-02", "window_start": "9am"}, "HH:MM"),
    ({"date": "2030-01-02", "window_start": "09:10"}, "15-minute boundary"),
    ({"date": "2030-01-02", "duration_min": 10}, "duration_min"),
    ({"date": "2030-01-02", "duration_min": True}, "whole number"),
    ({"date": "2030-01-02", "window_start": "16:00", "duration_min": 120}, "shorter than the meeting"),
])
def test_schedule_rejects_bad_config(raw, message):
    with pytest.raises(ValueError, match=message):
        materialize_config("schedule", raw, today=TODAY)


def test_decide_options_are_cleaned_deduped_and_capped():
    cfg = materialize_config("decide", {"options": ["  Thai  Palace ", "thai palace", "", 7, "B"]})
    assert cfg == {"options": ["Thai Palace", "B"]}
    with pytest.raises(ValueError, match="at most 20"):
        materialize_config("decide", {"options": [str(i) for i in range(21)]})


def test_unknown_kind_and_templates():
    with pytest.raises(ValueError):
        materialize_config("vote", {})
    assert stance_template("schedule") == {"available": [], "unavailable": [], "preferred": []}
    assert stance_template("decide")["top_pick"] is None


def test_parse_hhmm():
    assert parse_hhmm("09:05") == 545
    assert parse_hhmm("24:00") == 1440
    assert parse_hhmm("24:01") is None
    assert parse_hhmm("9:5") is None
    assert parse_hhmm(900) is None
