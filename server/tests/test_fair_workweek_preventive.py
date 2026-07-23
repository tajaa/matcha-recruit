"""Pure-logic tests for the preventive (write-time) Fair Workweek advisories
(no DB, no network) — the retrospective engine's own tests live in
`test_fair_workweek.py`."""

from datetime import datetime, timedelta, timezone

from app.matcha.services import fair_workweek as fw

NYC = fw._FAIR_WORKWEEK_ORDINANCES[("NY", "new-york-city")]
LA = fw._FAIR_WORKWEEK_ORDINANCES[("CA", "los-angeles")]

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _starts_in(days: float) -> datetime:
    return NOW + timedelta(days=days)


# ── unpublished shift → nothing ────────────────────────────────────────────

def test_draft_shift_never_gets_advisories():
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="retime", shift_published=False,
        starts_at=_starts_in(1), now=NOW, min_rest_gap_hours=2.0,
    )
    assert out == []


# ── notice-window advisory ─────────────────────────────────────────────────

def test_retime_inside_notice_window_flags_with_flat_estimate():
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="retime", shift_published=True,
        starts_at=_starts_in(3), now=NOW, min_rest_gap_hours=None,
    )
    notice = [v for v in out if v["check"] == "fair_workweek_notice"]
    assert len(notice) == 1
    assert notice[0]["severity"] == "advisory"
    assert "$" in notice[0]["message"]
    assert notice[0]["statute"] == NYC["citation"]


def test_retime_outside_notice_window_is_silent():
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="retime", shift_published=True,
        starts_at=_starts_in(30), now=NOW, min_rest_gap_hours=None,
    )
    assert not any(v["check"] == "fair_workweek_notice" for v in out)


def test_hours_at_rate_bracket_is_count_only_without_pay_rate():
    # LA's bracket is hours_at_rate; the write path never fetches pay_rate.
    out = fw.preventive_advisories(
        ordinance=LA, applicability="covered", event="assign", shift_published=True,
        starts_at=_starts_in(2), now=NOW, min_rest_gap_hours=None,
    )
    notice = [v for v in out if v["check"] == "fair_workweek_notice"]
    assert len(notice) == 1
    assert "$" not in notice[0]["message"]
    assert "depends on the employee" in notice[0]["message"]


def test_cancel_and_unassign_kinds_map_correctly():
    cancel = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="cancel", shift_published=True,
        starts_at=_starts_in(0.5), now=NOW, min_rest_gap_hours=None,
    )
    unassign = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="unassign", shift_published=True,
        starts_at=_starts_in(0.5), now=NOW, min_rest_gap_hours=None,
    )
    assert any(v["check"] == "fair_workweek_notice" for v in cancel)
    assert any(v["check"] == "fair_workweek_notice" for v in unassign)


def test_negative_notice_clamped_to_zero_still_matches_bracket():
    # Shift already started (e.g. a same-day retroactive edit) — must not
    # crash or produce a nonsensical negative notice_days.
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="retime", shift_published=True,
        starts_at=NOW - timedelta(hours=2), now=NOW, min_rest_gap_hours=None,
    )
    notice = [v for v in out if v["check"] == "fair_workweek_notice"]
    assert len(notice) == 1


# ── review_industry wording ────────────────────────────────────────────────

def test_review_industry_prefixes_message():
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="review_industry", event="retime", shift_published=True,
        starts_at=_starts_in(3), now=NOW, min_rest_gap_hours=None,
    )
    notice = [v for v in out if v["check"] == "fair_workweek_notice"]
    assert len(notice) == 1
    assert "verify your industry" in notice[0]["message"]


# ── clopening advisory ─────────────────────────────────────────────────────

def test_clopening_fires_under_rest_threshold():
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="assign", shift_published=True,
        starts_at=_starts_in(30), now=NOW, min_rest_gap_hours=8.0,  # NYC threshold is 11h
    )
    clopening = [v for v in out if v["check"] == "fair_workweek_clopening"]
    assert len(clopening) == 1
    assert "$100.00" in clopening[0]["message"]


def test_clopening_does_not_fire_at_or_above_threshold():
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="assign", shift_published=True,
        starts_at=_starts_in(30), now=NOW, min_rest_gap_hours=11.0,
    )
    assert not any(v["check"] == "fair_workweek_clopening" for v in out)


def test_clopening_ignored_for_non_clopening_events():
    # unassign/cancel can't CREATE a clopening.
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="unassign", shift_published=True,
        starts_at=_starts_in(30), now=NOW, min_rest_gap_hours=2.0,
    )
    assert not any(v["check"] == "fair_workweek_clopening" for v in out)


def test_clopening_needs_a_gap_value():
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="assign", shift_published=True,
        starts_at=_starts_in(30), now=NOW, min_rest_gap_hours=None,
    )
    assert not any(v["check"] == "fair_workweek_clopening" for v in out)


# ── never blocks ────────────────────────────────────────────────────────────

def test_every_advisory_is_advisory_severity_never_block():
    out = fw.preventive_advisories(
        ordinance=NYC, applicability="covered", event="assign", shift_published=True,
        starts_at=_starts_in(0.5), now=NOW, min_rest_gap_hours=1.0,
    )
    assert len(out) >= 2  # both notice and clopening should fire here
    assert all(v["severity"] == "advisory" for v in out)
    from app.matcha.services import schedule_compliance as sc
    assert sc.has_block(out) is False
