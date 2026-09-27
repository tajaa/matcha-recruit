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
        "So far Thai Palace is leading — 2 of 3 are in (2/3 responded)."
    )
    assert narrate.describe_change("decide", _dec(2, lead), _dec(3, {**lead, "ok": 3}, consensus=True)) == (
        "All 3 agree on Thai Palace. Sending invites to everyone."
    )
    assert narrate.describe_change("decide", _dec(1), _dec(2)) == (
        "Nothing without a veto yet (2/3 responded)."
    )
