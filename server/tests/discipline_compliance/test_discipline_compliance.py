"""Pure tests for the discipline compliance gate.

The gate decides whether a corrective action may legally issue, so the tests
bias toward the failure mode that is *invisible in production*: a confident
all-clear. A spurious block gets reported by an annoyed HR admin within a day; a
missed protected-leave overlap surfaces two years later in discovery. Every test
here that asserts "no block" also asserts an advisory took its place — nothing
is ever allowed to pass silently.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.matcha.services import discipline_compliance as dc
from app.matcha.services.legal_defense import validate_citations


def _leave(start, end=None, leave_type="medical", status="approved", id="L1"):
    return {
        "id": id,
        "leave_type": leave_type,
        "start_date": date.fromisoformat(start),
        "end_date": date.fromisoformat(end) if end else None,
        "status": status,
    }


def _pto(start, end, request_type="sick", status="approved", id="P1"):
    return {
        "id": id,
        "request_type": request_type,
        "start_date": date.fromisoformat(start),
        "end_date": date.fromisoformat(end),
        "status": status,
    }


def _d(*iso):
    return [date.fromisoformat(s) for s in iso]


# ── overlap_hits ────────────────────────────────────────────────────────

def test_overlap_exact_single_day():
    hits = dc.overlap_hits(_d("2026-03-10"), [_leave("2026-03-10", "2026-03-10")], [])
    assert len(hits) == 1
    assert hits[0]["dates"] == ["2026-03-10"]
    assert hits[0]["source"] == "leave_request"


def test_overlap_inside_multi_day_range():
    hits = dc.overlap_hits(_d("2026-03-12"), [_leave("2026-03-10", "2026-03-14")], [])
    assert hits[0]["dates"] == ["2026-03-12"]


def test_overlap_open_ended_leave_is_single_day_not_forever():
    """An open leave row must not swallow every future date.

    `end_date IS NULL` means "not yet closed out". Treating that as an unbounded
    window would let one stale row block every discipline the company ever
    issues for that employee — a gate nobody can use gets turned off.
    """
    hits = dc.overlap_hits(_d("2026-09-01"), [_leave("2026-03-10", None)], [])
    assert hits == []
    same_day = dc.overlap_hits(_d("2026-03-10"), [_leave("2026-03-10", None)], [])
    assert len(same_day) == 1


def test_no_overlap_when_dates_outside_window():
    hits = dc.overlap_hits(_d("2026-03-20"), [_leave("2026-03-10", "2026-03-14")], [])
    assert hits == []


def test_overlap_detects_sick_pto_separately_from_leave():
    hits = dc.overlap_hits(_d("2026-03-11"), [], [_pto("2026-03-10", "2026-03-12")])
    assert len(hits) == 1
    assert hits[0]["source"] == "pto_request"


def test_overlap_empty_occurrence_dates_finds_nothing():
    assert dc.overlap_hits([], [_leave("2026-03-10", "2026-03-14")], []) == []


def test_overlap_reports_only_the_matching_days():
    hits = dc.overlap_hits(
        _d("2026-03-09", "2026-03-11", "2026-03-20"),
        [_leave("2026-03-10", "2026-03-14")],
        [],
    )
    assert hits[0]["dates"] == ["2026-03-11"]


# ── build_verdict: the bright line ──────────────────────────────────────

def test_attendance_overlap_in_ca_blocks_and_cites_statute():
    v = dc.build_verdict(
        infraction_type="attendance",
        work_state="CA",
        overlaps=dc.overlap_hits(_d("2026-03-10"), [_leave("2026-03-10")], []),
        retaliation=[],
    )
    assert len(v["blocks"]) == 1
    assert v["blocks"][0]["code"] == "protected_leave_overlap"
    assert v["blocks"][0]["statute"] == "Cal. Lab. Code § 246.5(c)"


def test_attendance_overlap_in_unmapped_state_advises_never_blocks_and_never_clears():
    """The invariant that keeps a partial statute table honest.

    An unresearched state is not a permissive one. If this ever returns a clean
    verdict, the table's incompleteness has silently become an all-clear.
    """
    v = dc.build_verdict(
        infraction_type="attendance",
        work_state="TX",
        overlaps=dc.overlap_hits(_d("2026-03-10"), [_leave("2026-03-10")], []),
        retaliation=[],
    )
    assert v["blocks"] == []
    codes = {a["code"] for a in v["advisories"]}
    assert "leave_overlap_unmapped_state" in codes
    assert v["advisories"], "an unmapped state must never produce a silent pass"


def test_non_attendance_infraction_on_a_leave_day_advises_not_blocks():
    """Conduct is not the absence.

    Harassment that happened on a day the employee was also on leave is still
    disciplinable — the statutes bar counting the *absence*, not shielding the
    person. Blocking here would make the gate wrong in the other direction.
    """
    v = dc.build_verdict(
        infraction_type="harassment",
        work_state="CA",
        overlaps=dc.overlap_hits(_d("2026-03-10"), [_leave("2026-03-10")], []),
        retaliation=[],
    )
    assert v["blocks"] == []
    assert {a["code"] for a in v["advisories"]} == {"leave_overlap_non_attendance"}


def test_attendance_with_no_overlap_in_mapped_state_is_clean():
    v = dc.build_verdict(
        infraction_type="attendance", work_state="CA", overlaps=[], retaliation=[],
    )
    assert v["blocks"] == []
    assert v["advisories"] == []
    assert v["state_row"]["state"] == "CA"


def test_unmapped_state_with_no_overlap_still_advises():
    v = dc.build_verdict(
        infraction_type="attendance", work_state="TX", overlaps=[], retaliation=[],
    )
    assert v["blocks"] == []
    assert {a["code"] for a in v["advisories"]} == {"unmapped_state"}


def test_missing_work_state_is_treated_as_unmapped_not_clear():
    v = dc.build_verdict(
        infraction_type="attendance", work_state=None, overlaps=[], retaliation=[],
    )
    assert v["state_row"] is None
    assert {a["code"] for a in v["advisories"]} == {"unmapped_state"}


def test_state_is_case_and_whitespace_insensitive():
    assert dc.statute_for_state(" ca ")["state"] == "CA"
    assert dc.statute_for_state("California") is None  # only 2-letter codes map


# ── retaliation timing ──────────────────────────────────────────────────

def _event(days_before_occurrence, source="ir_incident", label="filed a safety report"):
    occurrence = date(2026, 6, 1)
    return {
        "id": "E1",
        "source": source,
        "label": label,
        "event_date": datetime.combine(
            occurrence - timedelta(days=days_before_occurrence),
            datetime.min.time(),
            tzinfo=timezone.utc,
        ),
    }


def test_protected_activity_inside_window_flags():
    hits = dc.retaliation_hits(_d("2026-06-01"), [_event(30)])
    assert len(hits) == 1
    assert hits[0]["days_before"] == 30


def test_protected_activity_outside_window_does_not_flag():
    hits = dc.retaliation_hits(_d("2026-06-01"), [_event(120)])
    assert hits == []


def test_protected_activity_after_the_conduct_does_not_flag():
    """A complaint filed after the misconduct cannot have motivated it."""
    hits = dc.retaliation_hits(_d("2026-06-01"), [_event(-10)])
    assert hits == []


def test_retaliation_advisory_never_becomes_a_block():
    v = dc.build_verdict(
        infraction_type="attendance",
        work_state="CA",
        overlaps=[],
        retaliation=dc.retaliation_hits(_d("2026-06-01"), [_event(5)]),
    )
    assert v["blocks"] == []
    assert {a["code"] for a in v["advisories"]} == {"retaliation_timing"}


# ── statute table shape ─────────────────────────────────────────────────

def test_statute_table_rows_are_well_formed():
    """Every row must carry a real citation — the table's whole value is that a
    block can point at a law. A row without one produces an unexplainable block."""
    assert dc._STATE_SICK_LEAVE_PROTECTIONS, "table must not be empty"
    for state, row in dc._STATE_SICK_LEAVE_PROTECTIONS.items():
        assert len(state) == 2 and state.isupper(), f"{state} is not a 2-letter code"
        assert row.get("statute", "").strip(), f"{state} has no statute citation"
        assert row.get("protection", "").strip(), f"{state} has no protection key"
        assert len(row.get("note", "")) > 30, f"{state} note must state the prohibition"


def test_california_is_present():
    """CA is the driving case: state-mandated sick leave cannot be disciplined,
    however faithfully the attendance policy was followed."""
    assert dc.statute_for_state("CA") is not None


# ── AI advisories ride along, they don't decide ─────────────────────────

def test_ai_advisories_are_appended_and_cannot_create_a_block():
    v = dc.build_verdict(
        infraction_type="attendance",
        work_state="CA",
        overlaps=[],
        retaliation=[],
        ai_advisories=[{"code": "ai_review", "detail": "tone reads as pretext"}],
    )
    assert v["blocks"] == []
    assert {a["code"] for a in v["advisories"]} == {"ai_review"}


# ── citation gate reuse contract ────────────────────────────────────────

def test_hallucinated_citations_are_dropped_by_the_shared_gate():
    """`discipline_ai` leans on this gate to keep invented record ids out of a
    legal document. Pinning the contract here so a change to it breaks loudly."""
    index = {"disc:real-1": {}, "policy:attendance": {}}
    clean, dropped = validate_citations(
        [{"point": "prior warning on file", "cited_ids": ["disc:real-1", "disc:invented-9"]}],
        index,
    )
    assert clean[0]["cited_ids"] == ["disc:real-1"]
    assert dropped == ["disc:invented-9"]
