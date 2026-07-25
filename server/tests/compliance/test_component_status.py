"""compliance_status — the per-clause statute component layer (reqcomp01). No DB.

SB 553's 5 obligations decompose one catalog row into a checklist. These pin
the two rules unique to that layer: the attest guard refuses only the
component that carries a derivation, never its siblings on the same statute
(the whole-key version of this guard would have blocked attestation on 4 of 5
components the moment 1 became derivable); and the new derivations obey the
same blind-never-violates invariant as the whole-requirement ones.
"""
import asyncio
from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.core.services.compliance_status import (
    COMPONENT_DERIVATIONS,
    STATUSES,
    _derive_wvp_incident_log,
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
        ctx={"wvp_training": {"assigned": 0, "completed": 0, "last_completed": None}})) is None


def test_training_incomplete_is_in_progress():
    status, ev = _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": {"assigned": 87, "completed": 40, "last_completed": None}}))
    assert status == "in_progress"
    assert (ev["completed"], ev["assigned"]) == (40, 87)


def test_training_complete_and_recent_is_compliant():
    status, ev = _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": {"assigned": 87, "completed": 87, "last_completed": date.today()}}))
    assert status == "compliant"
    assert ev["completed"] == 87


def test_training_complete_but_lapsed_is_non_compliant():
    stale = date.today() - timedelta(days=400)
    status, ev = _run(_derive_wvp_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"wvp_training": {"assigned": 87, "completed": 87, "last_completed": stale}}))
    assert status == "non_compliant"
    assert ev["last_completed"] == stale.isoformat()


# ── _derive_wvp_incident_log ─────────────────────────────────────────────────

def test_incident_log_no_matches_is_blind_not_clean():
    """Absence of a matching incident is not proof a log exists — could be no
    incidents, or incidents logged under different wording. Either way blind."""
    assert _run(_derive_wvp_incident_log(
        None, company_id="c", location_id=LOC, row={}, ctx={"violence_incidents": {}})) is None


def test_incident_log_with_matches_is_compliant():
    status, ev = _run(_derive_wvp_incident_log(
        None, company_id="c", location_id=LOC, row={},
        ctx={"violence_incidents": {LOC: {"total": 2}}}))
    assert status == "compliant"
    assert ev["matched_incidents"] == 2


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
    assert set(keys) == {"wvp_training", "wvp_incident_log"}


@pytest.mark.parametrize("status", STATUSES)
def test_status_vocabulary_matches_the_migration_check(status):
    assert status in ("compliant", "non_compliant", "in_progress", "unknown")


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


def test_attest_rejects_unknown_status_value():
    conn = _FakeConn(derivation_key=None)
    with pytest.raises(ValueError):
        _run(attest_component_status(
            conn, company_id=uuid4(), location_id=uuid4(), catalog_id=uuid4(),
            component_key="hazard_assessment", status="definitely_fine", note=None,
            actor_user_id=uuid4(),
        ))
