"""Unit tests for Analysis Pilot's platform-data builders — the pure shaping half.

No DB: each builder is one query plus a pure function, and the pure function is
where every invariant lives (zero-filled months, triangle collapse, role
assignment). The registry itself is asserted so a new source can't ship without
a feature gate.
"""

from datetime import date, datetime, timezone

from app.matcha.services import analysis_platform_sources as ps
from app.matcha.services.analysis_packs import insurance, mapping, parse


# --- monthly incident series --------------------------------------------------

def test_month_labels_walk_back_across_the_year_boundary():
    labels = ps.month_labels(date(2026, 2, 15), 4)
    assert labels == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_ir_monthly_zero_fills_quiet_months():
    """A month with no incidents must be 0, not absent — a gap would shorten the
    series against its own period labels and every trend computed from it would
    describe a different window than the axis claims."""
    rows = [{"month": date(2026, 7, 1), "incident_type": "injury", "n": 3},
            {"month": date(2026, 5, 1), "incident_type": "injury", "n": 1}]
    built = ps.ir_monthly_series(rows, date(2026, 7, 20))
    periods, series = built["periods"], built["series"]
    assert len(periods) == ps._IR_MONTHS
    assert periods[-1] == "2026-07"
    assert all(len(v) == len(periods) for v in series.values())
    total = series[ps._TOTAL_LABEL]
    assert total[periods.index("2026-07")] == 3
    assert total[periods.index("2026-06")] == 0        # quiet month, not missing
    assert total[periods.index("2026-05")] == 1


def test_ir_monthly_totals_cover_every_type_including_untracked_ones():
    rows = [{"month": date(2026, 7, 1), "incident_type": f"type_{i}", "n": i + 1}
            for i in range(ps._MAX_IR_TYPES + 3)]
    built = ps.ir_monthly_series(rows, date(2026, 7, 20))
    per_type = [k for k in built["series"] if k != ps._TOTAL_LABEL]
    assert len(per_type) == ps._MAX_IR_TYPES
    # the tail is folded into the total, never dropped from the analysis
    idx = built["periods"].index("2026-07")
    assert built["series"][ps._TOTAL_LABEL][idx] == sum(r["n"] for r in rows)
    assert any("remain counted" in w for w in built["warnings"])


def test_ir_monthly_ignores_rows_outside_the_window_and_null_types():
    rows = [{"month": date(2000, 1, 1), "incident_type": "injury", "n": 9},
            {"month": date(2026, 7, 1), "incident_type": None, "n": 2}]  # noqa: E501
    built = ps.ir_monthly_series(rows, date(2026, 7, 20))
    assert "Unclassified" in built["series"]
    assert sum(built["series"][ps._TOTAL_LABEL]) == 2


def test_ir_monthly_with_no_incidents_yields_no_series_at_all():
    """24 zeros is not a dataset, it is the absence of one. The route refuses to
    persist a build whose `series` is empty, so a company with no incidents must
    land there rather than getting a flat line the chat can cite as a finding."""
    assert ps.ir_monthly_series([], date(2026, 7, 20))["series"] == {}
    # rows that all fall outside the labelled window are the same case
    stale = [{"month": date(2000, 1, 1), "incident_type": "injury", "n": 9}]
    assert ps.ir_monthly_series(stale, date(2026, 7, 20))["series"] == {}


# --- loss runs ----------------------------------------------------------------

def _snap(label, valuation, paid, reserved, claims=4, open_=1, start="2024-01-01"):
    return {"policy_period_label": label, "policy_period_start": start,
            "valuation_date": valuation, "paid": paid, "reserved": reserved,
            "claim_count": claims, "open_count": open_, "created_at": valuation}


def test_loss_runs_keep_the_latest_valuation_of_each_period():
    """A loss run is a triangle — the same period re-valued over time. A series
    needs one value per period, and the latest valuation is the developed one."""
    snaps = [_snap("2024-25", "2025-01-01", 100, 50, start="2024-01-01"),
             _snap("2024-25", "2026-01-01", 180, 20, start="2024-01-01"),
             _snap("2023-24", "2025-06-01", 90, 10, start="2023-01-01")]
    built = ps.loss_run_series(snaps)
    assert built["periods"] == ["2023-24", "2024-25"]      # ordered by period start
    assert built["series"]["Paid"] == [90.0, 180.0]        # the 2025 valuation lost
    assert built["series"]["Incurred"] == [100.0, 200.0]
    assert any("collapsed" in w for w in built["warnings"])
    assert built["as_of"] == "2026-01-01"


def test_loss_runs_drop_all_null_columns():
    snaps = [_snap("2024-25", "2026-01-01", 100, 50, claims=None, open_=None)]
    built = ps.loss_run_series(snaps)
    assert "Claim count" not in built["series"] and "Open claims" not in built["series"]
    assert "Paid" in built["series"]
    # roles only name series that exist, so `applies()` can't count a role the
    # data doesn't carry
    assert set(built["roles"]) == set(built["series"])


def test_loss_runs_roles_make_the_insurance_pack_apply():
    built = ps.loss_run_series([_snap("2023-24", "2025-06-01", 90, 10),
                                _snap("2024-25", "2026-01-01", 180, 20)])
    normalized = parse.normalize(
        {"series": built["series"], "periods": built["periods"]},
        source_kind="platform", filename="Loss runs",
        roles_override=built["roles"], kind_override="loss_run")
    assert insurance.applies(normalized) is True
    assert normalized["kind"] == "loss_run"
    assert normalized["meta"]["source_kind"] == "platform"


def test_loss_runs_tolerate_junk_and_empty():
    assert ps.loss_run_series([])["series"] == {}
    assert ps.loss_run_series([{"policy_period_label": ""}])["series"] == {}


# --- registry -----------------------------------------------------------------

# --- scheduling weekly series --------------------------------------------------

def _shift(starts_at, *, hours=8.0, required=2, assigned=2, status="published"):
    ends_at = starts_at.replace(hour=min(starts_at.hour + int(hours), 23))
    return {"starts_at": starts_at, "ends_at": ends_at, "break_minutes": 0,
            "status": status, "required_staff": required, "assigned_count": assigned,
            "duration_hours": hours}


def test_schedule_weekly_zero_fills_quiet_weeks_and_flags_understaffing():
    as_of = date(2026, 3, 1)  # a Sunday
    shifts = [
        _shift(datetime(2026, 3, 1, 9, tzinfo=timezone.utc), hours=8.0, required=3, assigned=2),
        _shift(datetime(2026, 3, 1, 17, tzinfo=timezone.utc), hours=6.0, required=2, assigned=2),
    ]
    result = ps.schedule_weekly_series(shifts, [], as_of)
    assert result["periods"][-1] == "2026-03-01"
    idx = len(result["periods"]) - 1
    assert result["series"]["Shifts"][idx] == 2.0
    assert result["series"]["Scheduled hours"][idx] == 14.0
    assert result["series"]["Understaffed shifts"][idx] == 1.0
    # Every earlier week with nothing on file is a zero, not absent.
    assert len(result["periods"]) == ps._SCHEDULE_WEEKS
    assert result["series"]["Shifts"][0] == 0.0


def test_schedule_weekly_excludes_cancelled_shifts():
    """A cancelled shift contributes nothing — with no other activity that
    week (or any other), this is the all-zero case, same as `ir_monthly_series`
    with no incidents: no series at all, not a flat line of zeros."""
    as_of = date(2026, 3, 1)
    shifts = [_shift(datetime(2026, 3, 1, 9, tzinfo=timezone.utc), status="cancelled")]
    result = ps.schedule_weekly_series(shifts, [], as_of)
    assert result["series"] == {}


def test_schedule_weekly_counts_only_employer_initiated_changes():
    as_of = date(2026, 3, 1)
    changes = [
        {"employee_initiated": False, "created_at": datetime(2026, 3, 1, 12, tzinfo=timezone.utc)},
        {"employee_initiated": True, "created_at": datetime(2026, 3, 1, 12, tzinfo=timezone.utc)},
        {"employee_initiated": False, "created_at": None},  # unresolvable, must not crash
    ]
    result = ps.schedule_weekly_series([], changes, as_of)
    assert result["series"]["Employer-initiated changes"][-1] == 1.0


def test_schedule_weekly_with_nothing_on_file_yields_no_series():
    assert ps.schedule_weekly_series([], [], date(2026, 3, 1)) == {
        "series": {}, "periods": [], "roles": {}, "warnings": [], "as_of": "2026-03-01",
    }


def test_every_source_declares_a_real_feature_gate_and_kind():
    from app.core.feature_flags import DEFAULT_COMPANY_FEATURES

    assert ps.SOURCES, "registry must not be empty"
    keys = [s.key for s in ps.SOURCES]
    assert len(keys) == len(set(keys))
    for s in ps.SOURCES:
        assert s.required_feature in DEFAULT_COMPANY_FEATURES or s.required_feature in (
            "incidents", "employees")          # flipped on by tier flows, not in defaults
        assert s.kind in ("timeseries", "loss_run", "financial_statement", "inventory", "generic")
        assert callable(s.build)


def test_catalog_matches_the_registry_and_get_source_round_trips():
    cat = ps.catalog()
    assert [c["key"] for c in cat] == [s.key for s in ps.SOURCES]
    assert all(c["label"] and c["description"] for c in cat)
    assert ps.get_source("ir_monthly").kind == "timeseries"
    assert ps.get_source("nope") is None and ps.get_source(None) is None


def test_roles_assigned_by_the_builder_are_canonical():
    """Platform roles are assigned explicitly, not guessed by the lexicon — so
    they must still be vocabulary the packs recognize."""
    for role in ps._LOSS_ROLES.values():
        assert role in mapping.CANONICAL_ROLES


# --- line selection -----------------------------------------------------------

def test_pick_line_prefers_the_line_with_the_most_periods():
    """Hard-defaulting to `wc` told a company that records only GL loss runs it
    had none — the rows were there, on another line."""
    snaps = [_snap("2024-25", "2026-01-01", 1, 1), _snap("2023-24", "2025-01-01", 1, 1)]
    for s in snaps:
        s["line"] = "gl"
    snaps.append({**_snap("2024-25", "2026-01-01", 1, 1), "line": "wc"})
    assert ps.pick_line(snaps) == "gl"
    assert ps.pick_line([]) is None
    assert ps.pick_line([{"line": "", "policy_period_label": "x"}]) is None


def test_pick_line_is_deterministic_under_a_tie():
    snaps = [{**_snap("2024-25", "2026-01-01", 1, 1), "line": ln} for ln in ("wc", "auto")]
    assert ps.pick_line(snaps) == ps.pick_line(list(reversed(snaps))) == "auto"
