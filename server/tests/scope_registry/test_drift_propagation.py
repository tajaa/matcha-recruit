"""Drift → requirement propagation pure core. No DB."""
from datetime import datetime

from app.core.services.scope_registry.codify import affected_requirement_updates


def _drift(drift_id, change_type, citation="29 CFR 541.600", idx="AI1", dt=None):
    return {"drift_id": drift_id, "change_type": change_type, "citation": citation,
            "authority_index_id": idx, "detected_at": dt}


def _link(citation="29 CFR 541.600", idx="AI1", req="r1", prior="unchanged"):
    return {"authority_index_id": idx, "citation": citation,
            "requirement_id": req, "prior_change_status": prior}


def test_new_change_type_is_ignored():
    # A 'new' citation has no classification yet → never propagates.
    updates = affected_requirement_updates([_drift("d1", "new")], [_link()])
    assert updates == {}


def test_amended_maps_through_link():
    updates = affected_requirement_updates([_drift("d1", "amended")], [_link(req="r1")])
    assert set(updates) == {"r1"}
    assert updates["r1"]["change_type"] == "amended"
    assert updates["r1"]["prior_change_status"] == "unchanged"


def test_removed_maps_through_link():
    updates = affected_requirement_updates([_drift("d1", "removed")], [_link(req="r1")])
    assert updates["r1"]["change_type"] == "removed"


def test_no_matching_codification_is_noop():
    # drift citation with no scope_codifications link → nothing flagged.
    updates = affected_requirement_updates(
        [_drift("d1", "amended", citation="29 CFR 999.9")],
        [_link(citation="29 CFR 541.600")],
    )
    assert updates == {}


def test_two_drifts_one_requirement_latest_wins():
    early = _drift("d_old", "amended", dt=datetime(2026, 1, 1))
    late = _drift("d_new", "removed", dt=datetime(2026, 6, 1))
    # both drift rows resolve to the same requirement
    updates = affected_requirement_updates([early, late], [_link(req="r1")])
    assert set(updates) == {"r1"}
    assert updates["r1"]["drift_id"] == "d_new"  # latest detected_at
    assert updates["r1"]["change_type"] == "removed"


def test_prior_change_status_preserved():
    updates = affected_requirement_updates(
        [_drift("d1", "amended")], [_link(req="r1", prior="changed")],
    )
    assert updates["r1"]["prior_change_status"] == "changed"


def test_one_drift_fans_to_multiple_requirements():
    # Same federal citation codified into two jurisdictions' rows.
    links = [_link(req="r_fed"), _link(req="r_ca")]
    updates = affected_requirement_updates([_drift("d1", "amended")], links)
    assert set(updates) == {"r_fed", "r_ca"}
