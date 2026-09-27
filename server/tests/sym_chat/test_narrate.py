"""Shared feed lines (services/sym_chat/narrate.py) — exact template strings."""
from app.matcha.services.sym_chat import narrate


def _sched(responded, best=None, total=4, consensus=False):
    return {"kind": "schedule", "date": "2026-09-29", "total": total, "responded": responded,
            "best": best, "consensus": consensus}


def test_fmt_time_and_date():
    assert narrate.fmt_time("00:00") == "12:00 AM"
    assert narrate.fmt_time("12:30") == "12:30 PM"
    assert narrate.fmt_time("17:30") == "5:30 PM"
    assert narrate.fmt_date("2026-09-29") == "Tue, Sep 29"


def test_schedule_progress_line():
    new = _sched(3, {"start": "14:00", "end": "14:30", "count": 3})
    assert narrate.describe_change("schedule", _sched(2), new) == (
        "So far 2:00 PM looks best — 3 of 4 can make it (3/4 responded)."
    )


def test_schedule_consensus_line():
    new = _sched(4, {"start": "17:30", "end": "18:00", "count": 4}, consensus=True)
    assert narrate.describe_change("schedule", _sched(3), new) == (
        "All 4 agree on 5:30 PM on Tue, Sep 29. Sending invites to everyone."
    )


def test_no_line_when_nothing_material_changed():
    best = {"start": "14:00", "end": "14:30", "count": 2, "preferred": 0}
    old = _sched(2, best)
    new = _sched(2, {**best, "preferred": 1})  # only a preference moved
    assert narrate.describe_change("schedule", old, new) is None


def test_first_shape_always_narrates():
    assert narrate.describe_change("schedule", {}, _sched(0)) == "Waiting on 4 people."
    assert narrate.describe_change("schedule", None, _sched(0, total=1)) == "Waiting on 1 person."


def test_no_overlap_line():
    assert narrate.describe_change("schedule", _sched(1), _sched(2)) == (
        "No time works for everyone who's answered yet (2/4 responded)."
    )


def _dec(responded, leading=None, total=3, consensus=False):
    return {"kind": "decide", "total": total, "responded": responded, "leading": leading, "consensus": consensus}


def test_decide_lines():
    lead = {"name": "Thai Palace", "ok": 2, "top": 1, "vetoes": 0}
    assert narrate.describe_change("decide", _dec(1), _dec(2, lead)) == (
        "So far Thai Palace is leading — 2 of 3 in (2/3 responded)."
    )
    assert narrate.describe_change("decide", _dec(2, lead), _dec(3, {**lead, "ok": 3}, consensus=True)) == (
        "All 3 agree on Thai Palace. Sending invites to everyone."
    )
    assert narrate.describe_change("decide", _dec(1), _dec(2)) == (
        "Nothing without a veto yet (2/3 responded)."
    )


def test_describe_stance_schedule_lines():
    assert narrate.describe_stance("schedule", "Jordan", {
        "available": [{"start": "15:00", "end": "17:00"}], "unavailable": [], "preferred": [],
    }) == "Jordan can do 3:00 PM–5:00 PM."
    assert narrate.describe_stance("schedule", "Priya", {
        "available": [{"start": "16:00", "end": "18:00"}],
        "unavailable": [{"start": "15:00", "end": "15:30"}],
        "preferred": ["16:00"],
    }) == "Priya can't do 3:00 PM–3:30 PM. They can do 4:00 PM–6:00 PM. Prefers 4:00 PM."
    assert narrate.describe_stance("schedule", "Sam", {"available": [], "unavailable": [], "preferred": []}) is None


def test_describe_stance_decide_lines():
    assert narrate.describe_stance("decide", "Lee", {
        "proposals": ["Sushi Go"], "ok_with": ["Thai Palace"], "vetoes": ["Burger Barn"], "top_pick": "Sushi Go",
    }) == "Lee is in for Sushi Go and Thai Palace. Top pick: Sushi Go. They won't do Burger Barn."


def test_kickoff_and_confirmed_text():
    cfg = {"date": "2026-09-29", "window_start": "13:00", "window_end": "18:00", "duration_min": 30,
           "timezone": "America/Los_Angeles"}
    assert narrate.kickoff_text("schedule", cfg, "Maria", "Q4 sync") == (
        "Hi! Maria is finding a 30-minute slot on Tue, Sep 29 between 1:00 PM and 6:00 PM "
        "(America/Los_Angeles) (Q4 sync). When are you free? Just tell me in your own words — "
        "I'll handle the back-and-forth."
    )
    res = {"kind": "schedule", "date": "2026-09-29", "start": "16:00", "end": "16:30", "timezone": "America/Los_Angeles"}
    assert narrate.confirmed_text(res) == (
        "It's confirmed: 4:00 PM–4:30 PM on Tue, Sep 29 (America/Los_Angeles). "
        "Everyone's in — invites are on the way, nothing else to do."
    )


def test_is_nudge_about_matches_nudges_not_the_kickoff_option_list():
    kickoff = narrate.kickoff_text("decide", {"options": ["Thai Palace", "Sushi Go"]}, "Maria")
    assert not narrate.is_nudge_about(kickoff, "Thai Palace")
    shape = {"kind": "decide", "total": 3, "leading": {"name": "Thai Palace", "ok": 1, "top": 1, "vetoes": 0}}
    silent = narrate.nudge_text("decide", shape, responded=False)
    asked = narrate.nudge_text("decide", shape, responded=True)
    assert narrate.is_nudge_about(silent, "Thai Palace") and narrate.is_nudge_about(asked, "Thai Palace")
    assert not narrate.is_nudge_about(silent, "Sushi Go")
