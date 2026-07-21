"""Unit tests for Analysis Pilot's platform-data builders — the pure shaping half.

No DB: each builder is one query plus a pure function, and the pure function is
where every invariant lives (zero-filled months, triangle collapse, role
assignment). The registry itself is asserted so a new source can't ship without
a feature gate.
"""

from datetime import date

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
            {"month": date(2026, 7, 1), "incident_type": None, "n": 2}]
    built = ps.ir_monthly_series(rows, date(2026, 7, 20))
    assert "Unclassified" in built["series"]
    assert sum(built["series"][ps._TOTAL_LABEL]) == 2


def test_ir_monthly_empty_is_empty_not_a_flat_line_of_zeros_with_no_series():
    built = ps.ir_monthly_series([], date(2026, 7, 20))
    # the total series still exists (all zeros) — the route's "no data" check
    # keys on the query returning nothing, not on this shape
    assert built["series"][ps._TOTAL_LABEL] == [0.0] * ps._IR_MONTHS


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
