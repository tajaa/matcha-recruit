"""compliance_status — the per-clause statute component layer (reqcomp01). No DB.

SB 553's 5 obligations decompose one catalog row into a checklist. These pin
the two rules unique to that layer: the attest guard refuses only the
component that carries a derivation, never its siblings on the same statute
(the whole-key version of this guard would have blocked attestation on 4 of 5
components the moment 1 became derivable); and the new derivations obey the
same blind-never-violates invariant as the whole-requirement ones.

Also covers the annual-training lapse fix (MAX(completed_date) hid a
workforce-wide lapse behind one recent completion) and the violent-incident-log
derivation's removal (a text match is not proof the statute's log exists —
that clause is attest-only now, like written_plan/hazard_assessment).
"""
import asyncio
import inspect
from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.core.services import compliance_status as cs
from app.core.services.compliance_status import (
    CTX_GROUPS,
    COMPONENT_DERIVATIONS,
    DERIVATIONS,
    STATUSES,
    _context_groups_for,
    _derive_wvp_training,
    attest_component_status,
    component_derivation,
    derivable_component_keys,
    resolve_status,
    rollup,
)


def _run(coro):
    return asyncio.run(coro)


LOC = "loc-1"


def _wvp_ctx(assigned, completed, current_completed=None, completed_undated=0,
             oldest_completed=None, last_completed=None):
    """Fill in the fields _build_context's wvp_training query now selects.
    Defaults `current_completed` to `completed` (everyone current) unless the
    test is specifically exercising a lapse."""
    if current_completed is None:
        current_completed = completed
    return {
        "assigned": assigned, "completed": completed,
        "current_completed": current_completed, "completed_undated": completed_undated,
        "oldest_completed": oldest_completed, "last_completed": last_completed,
    }


# ── rollup (component checklist reuses the same pure function) ─────────────

def test_rollup_excludes_unknown():
    rows = [
        {"status": "compliant", "basis": "derived"},
        {"status": "compliant", "basis": "attested"},
        {"status": "unknown", "basis": None},
        {"status": "unknown", "basis": None},
        {"status": "unknown", "basis": None},
    ]
    r = rollup(rows)
    assert r["total"] == 5
    assert r["known"] == 2
    assert r["coverage_pct"] == 40


# ── _derive_wvp_training ─────────────────────────────────────────────────────

def test_training_blind_when_context_absent():
    assert _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={}, ctx={})) is None


def test_training_nothing_assigned_returns_none():
    assert _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": _wvp_ctx(assigned=0, completed=0)})) is None


def test_training_incomplete_is_in_progress():
    status, ev = _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": _wvp_ctx(assigned=87, completed=40)}))
    assert status == "in_progress"
    assert (ev["completed"], ev["assigned"]) == (40, 87)


def test_training_complete_and_current_is_compliant():
    today = date.today()
    status, ev = _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": _wvp_ctx(
            assigned=87, completed=87, current_completed=87, last_completed=today)}))
    assert status == "compliant"
    assert ev["completed"] == 87


def test_training_one_stale_completion_among_many_current_is_non_compliant():
    """The MAX(completed_date) regression: 88 assigned, 88 completed, but only
    1 of them is inside the 12-month window (a new hire trained yesterday) —
    the other 87 lapsed. MAX() alone would read this as compliant."""
    stale = date.today() - timedelta(days=400)
    status, ev = _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": _wvp_ctx(
            assigned=88, completed=88, current_completed=1, oldest_completed=stale,
            last_completed=date.today())}))
    assert status == "non_compliant"
    assert ev["lapsed"] == 87
    assert ev["oldest_completed"] == stale.isoformat()


def test_training_all_lapsed_is_non_compliant():
    stale = date.today() - timedelta(days=400)
    status, ev = _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": _wvp_ctx(
            assigned=87, completed=87, current_completed=0, oldest_completed=stale,
            last_completed=stale)}))
    assert status == "non_compliant"
    assert ev["lapsed"] == 87


def test_training_completed_but_undated_is_in_progress_not_compliant():
    """A completed record with no completed_date is neither proof of currency
    nor of lapse — it cannot satisfy the annual cycle, so it stays blind on
    currency (in_progress), not a clean bill of health."""
    status, ev = _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": _wvp_ctx(
            assigned=10, completed=10, current_completed=7, completed_undated=3)}))
    assert status == "in_progress"
    assert ev["undated"] == 3


def test_training_lapsed_outranks_undated():
    """Positive proof of a lapse wins over an unprovable-currency record —
    non_compliant is a stronger claim than in_progress and must not be masked
    by an unrelated undated record."""
    stale = date.today() - timedelta(days=400)
    status, ev = _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": _wvp_ctx(
            assigned=10, completed=10, current_completed=6, completed_undated=1,
            oldest_completed=stale)}))
    assert status == "non_compliant"
    assert ev["lapsed"] == 3


# ── violent_incident_log is attest-only (the ILIKE-derivation removal) ─────

def test_incident_log_has_no_derivation():
    """Used to be `compliant` on a single ILIKE match against ir_incidents —
    a matching incident title proves an incident was mentioned, not that the
    statute's log (required fields + 5-year retention) exists. Removed
    entirely; the clause is attest-only now."""
    assert "wvp_incident_log" not in COMPONENT_DERIVATIONS
    assert not hasattr(cs, "_derive_wvp_incident_log")


# ── registry integrity ───────────────────────────────────────────────────────

def test_component_derivations_are_self_consistent():
    for key, d in COMPONENT_DERIVATIONS.items():
        assert d.key == key
        assert d.label


def test_component_required_feature_gates_are_declared():
    """An ungated component derivation would read an unsold module's absence
    as a clean record — every entry must name the feature it depends on."""
    for d in COMPONENT_DERIVATIONS.values():
        assert d.required_feature is not None


def test_component_derivation_lookup():
    assert component_derivation(None) is None
    assert component_derivation("nonexistent-key") is None
    assert component_derivation("wvp_training") is COMPONENT_DERIVATIONS["wvp_training"]


def test_derivable_component_keys_are_sorted_and_real():
    keys = derivable_component_keys()
    assert keys == sorted(keys)
    assert set(keys) == {"wvp_training"}


@pytest.mark.parametrize("status", STATUSES)
def test_status_vocabulary_matches_the_migration_check(status):
    assert status in ("compliant", "non_compliant", "in_progress", "unknown")


# ── context_group / source_label — the _build_context narrowing (B1) ───────

def test_every_derivation_declares_a_context_group():
    """Without a declared context_group, a new derivation reads an unbuilt
    ctx group (whichever _build_context call happened to narrow to something
    else) and silently comes back blind — indistinguishable from an unsold
    feature, but for the wrong reason."""
    for registry in (DERIVATIONS, COMPONENT_DERIVATIONS):
        for d in registry.values():
            assert d.context_group in CTX_GROUPS, d.key


def test_every_component_derivation_declares_a_source_label():
    """The audit-reveal UI's 'Screening <source>' strip reads this — an
    unset source_label falls through to the generic 'company records',
    which is wrong for a derivation that DOES read a specific table."""
    for d in COMPONENT_DERIVATIONS.values():
        assert d.source_label


def test_context_groups_for_ignores_unknown_keys():
    assert _context_groups_for(DERIVATIONS, ["nonexistent", None]) == set()


def test_context_groups_for_is_empty_for_no_candidates():
    assert _context_groups_for(DERIVATIONS, []) == set()


def test_context_groups_for_resolves_known_keys():
    assert _context_groups_for(COMPONENT_DERIVATIONS, ["wvp_training"]) == {"wvp_training"}
    assert _context_groups_for(DERIVATIONS, ["state_minimum_wage", "injury_illness_recordkeeping"]) \
        == {"employees", "incidents"}


# ── `derivable` must be registry-resolved, not a bare derivation_key check ──
# (the drift guard: a catalog row can carry a stale/dropped derivation_key —
# exactly what wvp_incident_log became — and the attest button + the server's
# 409 must never disagree about whether a component is derivable.)

def test_derivable_is_registry_resolved_in_service_and_route():
    import app.core.routes.compliance.components as components_route

    bad_pattern = 'derivation_key"] is not None'
    assert bad_pattern not in inspect.getsource(cs.get_component_checklist)
    assert bad_pattern not in inspect.getsource(components_route)


# ── reconcile candidate queries are DISTINCT + correctly scoped (A4/A5) ─────

def test_component_reconcile_candidate_query_is_distinct():
    assert "SELECT DISTINCT" in inspect.getsource(cs.reconcile_component_status)


def test_component_reconcile_existing_map_is_scoped_to_component_rows():
    assert "component_key IS NOT NULL" in inspect.getsource(cs.reconcile_component_status)


# ── resolve_status precedence, reused unchanged by the component layer ──────

def test_derived_outranks_attestation_and_preserves_it():
    status, basis, evidence = resolve_status(
        ("compliant", {"rule": "annual WVP training complete"}),
        {"status": "non_compliant", "note": "we think we're behind", "at": "2026-01-01T00:00:00"},
    )
    assert (status, basis) == ("compliant", "derived")
    assert evidence["superseded_attestation"]["status"] == "non_compliant"


# ── attest_component_status: the per-component guard (a fake conn, not a real
# DB — the guard logic is what's under test, not asyncpg) ───────────────────

class _FakeConn:
    """Answers exactly the 3 calls attest_component_status makes, in order:
    fetchrow (component lookup) -> fetchval (prev status) -> execute x2."""

    def __init__(self, derivation_key):
        self._derivation_key = derivation_key

    async def fetchrow(self, query, *args):
        assert "requirement_components" in query
        return {"derivation_key": self._derivation_key}

    async def fetchval(self, query, *args):
        return None

    async def execute(self, query, *args):
        return None


def test_attest_refused_on_derivable_component():
    """The whole point of this layer: refusal is keyed on THIS component's
    derivation_key, not the parent statute's regulation_key."""
    conn = _FakeConn(derivation_key="wvp_training")
    with pytest.raises(PermissionError):
        _run(attest_component_status(
            conn, company_id=uuid4(), location_id=uuid4(), catalog_id=uuid4(),
            component_key="annual_training", status="compliant", note=None,
            actor_user_id=uuid4(),
        ))


def test_attest_allowed_on_sibling_component():
    """Regression test for the whole-key guard bug: hazard_assessment (no
    derivation_key) on the SAME requirement as annual_training must stay
    attestable even though its sibling is derivable. Reusing
    attest_requirement_status's `regulation_key in DERIVATIONS` check here
    would refuse this the moment ANY component of the statute became
    derivable."""
    conn = _FakeConn(derivation_key=None)
    result = _run(attest_component_status(
        conn, company_id=uuid4(), location_id=uuid4(), catalog_id=uuid4(),
        component_key="hazard_assessment", status="compliant", note="site walked",
        actor_user_id=uuid4(),
    ))
    assert result == {"status": "compliant", "basis": "attested"}


def test_attest_allowed_on_violent_incident_log_now_that_it_is_attest_only():
    """Regression for dropping the wvp_incident_log derivation: this clause
    used to be refused (derivable) — it must now be attestable like any other
    attest-only component."""
    conn = _FakeConn(derivation_key=None)
    result = _run(attest_component_status(
        conn, company_id=uuid4(), location_id=uuid4(), catalog_id=uuid4(),
        component_key="violent_incident_log", status="compliant", note="log deployed",
        actor_user_id=uuid4(),
    ))
    assert result == {"status": "compliant", "basis": "attested"}


def test_attest_rejects_unknown_status_value():
    conn = _FakeConn(derivation_key=None)
    with pytest.raises(ValueError):
        _run(attest_component_status(
            conn, company_id=uuid4(), location_id=uuid4(), catalog_id=uuid4(),
            component_key="hazard_assessment", status="definitely_fine", note=None,
            actor_user_id=uuid4(),
        ))
