"""Deterministic consensus roll-up (services/sym_chat/aggregate.py)."""
from datetime import date

from app.matcha.services.sym_chat import aggregate
from app.matcha.services.sym_chat.kinds import materialize_config

SCHED = materialize_config(
    "schedule",
    {"date": "2030-01-15", "window_start": "13:00", "window_end": "18:00", "duration_min": 30},
    today=date(2030, 1, 1),
)


def _p(stance):
    return {"stance": stance}


def _avail(*spans, unavailable=(), preferred=()):
    return {
        "available": [{"start": s, "end": e} for s, e in spans],
        "unavailable": [{"start": s, "end": e} for s, e in unavailable],
        "preferred": list(preferred),
    }


def test_schedule_empty_chat_waits_on_everyone():
    shape = aggregate.compute_shape("schedule", SCHED, [_p(None), _p(None), _p(None)])
    assert shape["total"] == 3 and shape["responded"] == 0
    assert shape["best"] is None and not shape["consensus"]


def test_schedule_best_is_max_coverage_then_earliest():
    shape = aggregate.compute_shape("schedule", SCHED, [
        _p(_avail(("14:00", "16:00"))),
        _p(_avail(("15:00", "17:00"))),
        _p(None),
    ])
    assert shape["responded"] == 2
    assert shape["best"]["start"] == "15:00" and shape["best"]["count"] == 2
    assert not shape["consensus"]  # one person hasn't answered


def test_schedule_unavailable_carves_out_an_available_window():
    shape = aggregate.compute_shape("schedule", SCHED, [
        _p(_avail(("13:00", "18:00"), unavailable=[("13:00", "15:15")])),
        _p(_avail(("13:00", "18:00"))),
    ])
    # 15:00-15:30 overlaps the 15:15 unavailable end → first full slot is 15:15.
    assert shape["best"]["start"] == "15:15"
    assert shape["consensus"]


def test_schedule_preferred_breaks_count_ties():
    shape = aggregate.compute_shape("schedule", SCHED, [
        _p(_avail(("13:00", "18:00"), preferred=["16:30"])),
        _p(_avail(("13:00", "18:00"), preferred=["16:40"])),  # rounds down onto 16:30
    ])
    assert shape["best"]["start"] == "16:30" and shape["best"]["preferred"] == 2
    assert shape["consensus"]


def test_schedule_no_overlap_means_no_consensus():
    shape = aggregate.compute_shape("schedule", SCHED, [
        _p(_avail(("13:00", "14:00"))),
        _p(_avail(("16:00", "17:00"))),
    ])
    assert shape["responded"] == 2
    assert shape["best"]["count"] == 1
    assert not shape["consensus"]
    assert aggregate.resolution_for("schedule", SCHED, shape) is None


def test_schedule_resolution_carries_date_and_timezone():
    shape = aggregate.compute_shape("schedule", SCHED, [_p(_avail(("17:00", "18:00")))] * 2)
    assert aggregate.resolution_for("schedule", SCHED, shape) == {
        "kind": "schedule", "date": "2030-01-15", "start": "17:00", "end": "17:30",
        "timezone": "America/Los_Angeles",
    }


DECIDE = {"options": ["Thai Palace", "Burger Barn"]}


def _d(proposals=(), ok_with=(), vetoes=(), top_pick=None):
    return {"proposals": list(proposals), "ok_with": list(ok_with), "vetoes": list(vetoes), "top_pick": top_pick}


def test_decide_leader_is_vetoless_most_ok():
    shape = aggregate.compute_shape("decide", DECIDE, [
        _p(_d(ok_with=["Thai Palace", "Burger Barn"])),
        _p(_d(ok_with=["Burger Barn"], vetoes=["Thai Palace"])),
    ])
    names = [o["name"] for o in shape["options"]]
    assert names == ["Thai Palace", "Burger Barn"]
    assert shape["leading"]["name"] == "Burger Barn" and shape["leading"]["ok"] == 2
    assert shape["consensus"]
    assert aggregate.resolution_for("decide", DECIDE, shape) == {"kind": "decide", "choice": "Burger Barn"}


def test_decide_proposals_add_options_first_seen_and_case_insensitive():
    shape = aggregate.compute_shape("decide", DECIDE, [
        _p(_d(proposals=["Sushi Go"], top_pick="Sushi Go")),
        _p(_d(ok_with=["sushi go"])),
        _p(None),
    ])
    assert [o["name"] for o in shape["options"]] == ["Thai Palace", "Burger Barn", "Sushi Go"]
    sushi = shape["options"][2]
    assert sushi["ok"] == 2 and sushi["top"] == 1
    assert shape["leading"]["name"] == "Sushi Go"
    assert not shape["consensus"]  # third person hasn't answered


def test_decide_top_pick_breaks_ties_and_vetoes_alone_do_not_create_options():
    shape = aggregate.compute_shape("decide", {"options": []}, [
        _p(_d(ok_with=["A", "B"], top_pick="B", vetoes=["Z"])),
        _p(_d(ok_with=["A", "B"])),
    ])
    assert [o["name"] for o in shape["options"]] == ["A", "B"]
    assert shape["leading"]["name"] == "B"


def test_decide_everything_vetoed_has_no_leader():
    shape = aggregate.compute_shape("decide", DECIDE, [
        _p(_d(ok_with=["Thai Palace"], vetoes=["Burger Barn"])),
        _p(_d(ok_with=["Burger Barn"], vetoes=["Thai Palace"])),
    ])
    assert shape["leading"] is None and not shape["consensus"]
