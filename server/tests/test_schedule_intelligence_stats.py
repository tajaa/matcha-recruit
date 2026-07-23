"""Pure-logic tests for Schedule Intelligence (no DB, no network).

DB assembly (`services/schedule_intelligence.py`) is exercised manually on dev
DB — see the plan's verification section.
"""

from datetime import date, datetime, timedelta, timezone

from app.matcha.services import schedule_intelligence_stats as sis


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


# ── match_incidents_to_shifts ─────────────────────────────────────────────

def test_match_incidents_to_shifts_by_location_and_time():
    shifts = [
        {"id": "s1", "location_id": "loc1",
         "starts_at": _dt("2026-01-01T09:00:00+00:00"), "ends_at": _dt("2026-01-01T17:00:00+00:00")},
        {"id": "s2", "location_id": "loc2",
         "starts_at": _dt("2026-01-01T09:00:00+00:00"), "ends_at": _dt("2026-01-01T17:00:00+00:00")},
    ]
    incidents = [
        {"id": "i1", "location_id": "loc1", "occurred_at": _dt("2026-01-01T12:00:00+00:00")},
        {"id": "i2", "location_id": "loc1", "occurred_at": _dt("2026-01-02T12:00:00+00:00")},  # no covering shift
        {"id": "i3", "location_id": None, "occurred_at": _dt("2026-01-01T12:00:00+00:00")},  # no location
    ]
    result = sis.match_incidents_to_shifts(incidents, shifts)
    assert result["matches"]["i1"] == "s1"
    assert result["matches"]["i2"] is None
    assert result["matches"]["i3"] is None
    assert result["unmatched_count"] == 2


def test_match_incidents_to_shifts_naive_occurred_at_treated_as_utc():
    shifts = [{"id": "s1", "location_id": "loc1",
               "starts_at": _dt("2026-01-01T09:00:00+00:00"), "ends_at": _dt("2026-01-01T17:00:00+00:00")}]
    incidents = [{"id": "i1", "location_id": "loc1", "occurred_at": datetime(2026, 1, 1, 12, 0, 0)}]  # naive
    result = sis.match_incidents_to_shifts(incidents, shifts)
    assert result["matches"]["i1"] == "s1"


# ── small_n_guard ──────────────────────────────────────────────────────────

def test_small_n_guard_suppresses_below_thresholds():
    assert sis.small_n_guard(3, 100) is not None
    assert sis.small_n_guard(20, 10) is not None
    assert sis.small_n_guard(20, 100) is None


# ── staffing_ratio_split / window_split ───────────────────────────────────

def test_staffing_ratio_split_excludes_cancelled_and_splits_incidents():
    shifts = [
        {"id": "s1", "status": "published", "required_staff": 2, "assigned_count": 1},  # understaffed
        {"id": "s2", "status": "published", "required_staff": 2, "assigned_count": 2},  # adequate
        {"id": "s3", "status": "cancelled", "required_staff": 2, "assigned_count": 0},  # excluded
    ]
    matches = {"i1": "s1", "i2": "s2", "i3": None}
    result = sis.staffing_ratio_split(shifts, matches)
    assert result["understaffed"]["shifts"] == 1
    assert result["understaffed"]["incidents"] == 1
    assert result["adequate"]["shifts"] == 1
    assert result["adequate"]["incidents"] == 1


def test_window_split_night_vs_day():
    night = _dt("2026-01-01T23:00:00+00:00")
    day = _dt("2026-01-01T09:00:00+00:00")
    shifts = [
        {"id": "s1", "status": "published", "starts_at": night},
        {"id": "s2", "status": "published", "starts_at": day},
    ]
    matches = {"i1": "s1"}
    result = sis.window_split(shifts, matches)
    assert result["night"]["shifts"] == 1 and result["night"]["incidents"] == 1
    assert result["day"]["shifts"] == 1 and result["day"]["incidents"] == 0


# ── rest gap / consecutive days ───────────────────────────────────────────

def test_min_rest_gap_hours():
    windows = [(_dt("2026-01-01T09:00:00+00:00"), _dt("2026-01-01T17:00:00+00:00"))]
    gap = sis.min_rest_gap_hours(windows, _dt("2026-01-02T03:00:00+00:00"), _dt("2026-01-02T11:00:00+00:00"))
    assert gap == 10.0


def test_min_rest_gap_hours_no_adjacent_shift():
    assert sis.min_rest_gap_hours([], _dt("2026-01-02T03:00:00+00:00"), _dt("2026-01-02T11:00:00+00:00")) is None


def test_consecutive_scheduled_days():
    d = date(2026, 1, 10)
    days = [d - timedelta(days=i) for i in range(5)]
    assert sis.consecutive_scheduled_days(days, d) == 5
    assert sis.consecutive_scheduled_days([d - timedelta(days=2)], d) == 1  # gap breaks the streak


# ── instability metrics / pretext flags ───────────────────────────────────

def test_instability_metrics_excludes_employee_initiated_and_flags_short_notice():
    rows = [
        {"action": "shift.update", "employee_initiated": False, "notice_hours": 24.0, "costable": True},
        {"action": "shift.update", "employee_initiated": False, "notice_hours": 200.0, "costable": True},
        {"action": "assignment.delete", "employee_initiated": True, "notice_hours": 5.0, "costable": True},
        {"action": "shift.update", "employee_initiated": False, "notice_hours": None, "costable": False},
    ]
    metrics = sis.instability_metrics(rows, weekly_hours=[30.0, 40.0, 20.0])
    assert metrics["employer_changes"] == 3  # excludes the employee-initiated row
    assert metrics["short_notice_changes"] == 1  # only the 24h-notice row is < 72h
    assert metrics["uncostable_legacy"] == 1
    assert metrics["weekly_hours_sigma"] is not None


def test_weekly_hours_sigma_needs_two_points():
    assert sis.weekly_hours_sigma([40.0]) is None
    assert sis.weekly_hours_sigma([30.0, 50.0]) == 10.0


def test_pretext_flags_requires_two_signals():
    metrics_low = {"employer_changes": 5, "short_notice_changes": 0, "weekly_hours_sigma": 1.0}
    metrics_high = {"employer_changes": 6, "short_notice_changes": 4, "weekly_hours_sigma": 9.0}
    records = [
        {"id": "d1", "employee_id": "e1", "infraction_type": "attendance", "issued_date": "2026-01-01"},
        {"id": "d2", "employee_id": "e2", "infraction_type": "attendance", "issued_date": "2026-01-01"},
    ]
    flagged = sis.pretext_flags(records, {"e1": metrics_low, "e2": metrics_high})
    assert len(flagged) == 1
    assert flagged[0]["discipline_record_id"] == "d2"
    assert len(flagged[0]["signals"]) >= 2


# ── qualified_headcount ────────────────────────────────────────────────────

def test_qualified_headcount_splits_lapsed():
    result = sis.qualified_headcount(["e1", "e2", "e3"], {"e2": [{"source": "training", "item": "CPR"}]})
    assert result["assigned"] == 3
    assert result["qualified"] == 2
    assert result["lapsed_employee_ids"] == ["e2"]
