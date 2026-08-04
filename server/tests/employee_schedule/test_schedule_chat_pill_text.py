"""proposal_text's honesty line — must read the pre-computed
`proposal['rules_unmapped']` flag (set once in `build_proposal` from
`shift_compliance._approved_db_rules`), never re-derive via
`schedule_compliance.rules_summary(state)` with no `db_rules` arg, which
always reports "unmapped" for a non-curated state even when an approved
catalog extraction evaluated every shift. Pure — no DB, no Gemini.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_pill_text.py -q
"""

from datetime import datetime, timezone

from app.matcha.services.scheduling.schedule_chat import proposal_text, result_text, schedule_strip

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


# ── schedule_strip / result_text's rendered-bar tokens ───────────────────
# The confirm pill's [[shift:id:date]] link opens the real scheduler; the
# bar tokens below it are what client/.../ChannelView/systemContent.tsx
# renders as an actual colored hour-ruler grid — see schedule_strip's own
# docstring for why the token payload is digits-only. Backend emits raw
# minutes, unrounded; clamping/rounding for display is the client's job.


def _shift(h_start, h_end, names=("Aisha Kim",), label="opener", day=10, minute_start=0, minute_end=0):
    starts = datetime(2026, 8, day, h_start, minute_start, tzinfo=timezone.utc)
    overnight = h_end <= h_start
    ends_day = day + 1 if overnight else day
    ends = datetime(2026, 8, ends_day, h_end % 24, minute_end, tzinfo=timezone.utc)
    return {
        "id": "s1", "date": starts.date().isoformat(), "label": label,
        "when": "Mon Aug 10", "assignee_names": list(names),
        "starts_at": starts, "ends_at": ends,
    }


def test_schedule_strip_empty_when_nothing_created():
    assert schedule_strip([]) == ""


def test_shift_emits_exact_minute_bar_token():
    strip = schedule_strip([_shift(8, 16)])
    assert "[[bar:480:960:0]]" in strip
    assert strip.count("[[barruler]]") == 1
    assert "Mon Aug 10" in strip


def test_color_rotates_per_shift_line():
    # Each shift lands on its own day, so every shift also gets its own
    # date+ruler pair (3 lines/shift): bar line sits at index i*3 + 2.
    shifts = [_shift(8, 10, day=d) for d in range(10, 15)]
    strip = schedule_strip(shifts)
    lines = strip.splitlines()
    for i in range(5):
        assert f":{i % 4}]]" in lines[i * 3 + 2]


def test_unstaffed_shift_gets_the_reserved_color_index():
    strip = schedule_strip([_shift(8, 16, names=())])
    assert "[[bar:480:960:4]]" in strip
    assert "open" in strip


def test_overnight_shift_end_minute_exceeds_a_day_and_flags_label():
    strip = schedule_strip([_shift(20, 2)])  # 20:00 -> 02:00 next day
    assert "[[bar:1200:1560:0]]" in strip
    assert "→+1d" in strip


def test_shift_outside_display_window_still_emits_real_minutes():
    # No clamping backend-side — 4:00-23:00 emits its actual minutes;
    # display clamping is the client's job.
    strip = schedule_strip([_shift(4, 23)])
    assert "[[bar:240:1380:0]]" in strip


def test_seven_line_cap_with_overflow_note():
    shifts = [_shift(8, 10, day=10 + i) for i in range(9)]
    strip = schedule_strip(shifts)
    lines = strip.splitlines()
    assert len([l for l in lines if l.startswith("[[bar:")]) == 7
    assert "and 2 more" in lines[-1]


def test_partial_hour_uses_exact_minutes_no_rounding():
    strip = schedule_strip([_shift(8, 16, minute_start=30, minute_end=30)])
    assert "[[bar:510:990:0]]" in strip


def test_two_dates_get_two_rulers_same_date_gets_one():
    shifts = [_shift(8, 10, day=10), _shift(12, 14, day=10), _shift(8, 10, day=11)]
    strip = schedule_strip(shifts)
    assert strip.count("[[barruler]]") == 2
    assert strip.count("Mon Aug 10") == 1
    assert strip.count("Tue Aug 11") == 1
    assert strip.count("[[bar:") == 3


def test_result_text_includes_link_token_and_bars():
    shifts = [_shift(8, 16)]
    text = result_text(shifts, [])
    assert "[[shift:s1:2026-08-10]]" in text
    assert "[[barruler]]" in text
    assert "[[bar:480:960:0]]" in text


def test_result_text_omits_bars_when_nothing_created():
    text = result_text([], [{"name": "Aisha Kim", "label": "opener", "reason": "conflict"}])
    assert "[[bar" not in text
