"""compliance_status — the pure rules behind per-requirement status. No DB.

These pin the three claims the whole risk layer rests on: unknown never scores
as compliant, a deterministic fact outranks an opinion (without erasing it), and
a feature we cannot see through is a blind spot rather than a violation.
"""
import asyncio

import pytest

from app.core.services.compliance_status import (
    DERIVATIONS,
    STATUSES,
    _derive_exempt_salary,
    _derive_harassment_training,
    _derive_injury_recordkeeping,
    _derive_minimum_wage,
    biometrics_verdict,
    derivable_keys,
    pay_equity_verdict,
    pay_transparency_verdict,
    resolve_status,
    rollup,
)


def _run(coro):
    return asyncio.run(coro)


def _emp(name, cls, rate):
    first, _, last = name.partition(" ")
    return {"first_name": first, "last_name": last, "pay_classification": cls, "pay_rate": rate}


# ── resolve_status: precedence ──────────────────────────────────────────────

def test_nothing_known_is_unknown_not_compliant():
    """The load-bearing one. A blind spot scored as clean is how an underwriter
    gets a number that understates the book."""
    status, basis, evidence = resolve_status(None, None)
    assert status == "unknown"
    assert basis is None
    assert evidence == {}


def test_derivation_wins_over_attestation():
    status, basis, _ = resolve_status(
        ("non_compliant", {"rule": "pay below floor"}),
        {"status": "compliant", "note": "we're fine"},
    )
    assert (status, basis) == ("non_compliant", "derived")


def test_a_superseded_attestation_is_preserved_not_erased():
    """"We said compliant, payroll says otherwise" is the trail an ER case
    needs — the disagreement must stay visible."""
    _, _, evidence = resolve_status(
        ("non_compliant", {"rule": "pay below floor"}),
        {"status": "compliant", "note": "we're fine", "at": "2026-07-01T00:00:00"},
    )
    assert evidence["superseded_attestation"]["status"] == "compliant"
    assert evidence["superseded_attestation"]["note"] == "we're fine"


def test_an_agreeing_attestation_is_not_recorded_as_superseded():
    _, _, evidence = resolve_status(
        ("compliant", {"rule": "pay at or above floor"}),
        {"status": "compliant", "note": "yes"},
    )
    assert "superseded_attestation" not in evidence


def test_attestation_stands_when_the_system_is_blind():
    status, basis, evidence = resolve_status(None, {"status": "compliant", "note": "posted it"})
    assert (status, basis) == ("compliant", "attested")
    assert evidence["note"] == "posted it"


def test_an_empty_attestation_does_not_become_a_status():
    status, basis, _ = resolve_status(None, {"status": None, "note": "hmm"})
    assert (status, basis) == ("unknown", None)


# ── rollup ──────────────────────────────────────────────────────────────────

def test_rollup_counts_and_coverage_excludes_unknown():
    r = rollup([
        {"status": "compliant", "basis": "derived"},
        {"status": "non_compliant", "basis": "derived"},
        {"status": "compliant", "basis": "attested"},
        {"status": "unknown", "basis": None},
    ])
    assert r["total"] == 4
    assert r["known"] == 3
    assert r["coverage_pct"] == 75
    assert r["derived"] == 2
    assert r["attested"] == 1
    assert r["count_non_compliant"] == 1
    assert r["count_unknown"] == 1


def test_rollup_of_nothing_reports_null_coverage_not_100():
    r = rollup([])
    assert r["total"] == 0
    assert r["coverage_pct"] is None


def test_all_unknown_is_zero_coverage():
    r = rollup([{"status": "unknown", "basis": None}] * 3)
    assert r["coverage_pct"] == 0


# ── derivations ─────────────────────────────────────────────────────────────

LOC = "loc-1"


def test_minimum_wage_flags_underpaid_hourly_staff():
    ctx = {"employees": {LOC: [_emp("Ada L", "hourly", 15.0), _emp("Bo M", "hourly", 20.0)]}}
    out = _run(_derive_minimum_wage(
        None, company_id="c", location_id=LOC, row={"numeric_value": 16.5}, ctx=ctx))
    status, ev = out
    assert status == "non_compliant"
    assert ev["violations"] == 1
    assert ev["employees_checked"] == 2
    assert ev["examples"][0]["name"] == "Ada L"


def test_minimum_wage_clean_when_everyone_is_at_or_above():
    """At the floor exactly is compliant — the statute says 'not less than'."""
    ctx = {"employees": {LOC: [_emp("Ada L", "hourly", 16.5)]}}
    status, ev = _run(_derive_minimum_wage(
        None, company_id="c", location_id=LOC, row={"numeric_value": 16.5}, ctx=ctx))
    assert status == "compliant"
    assert ev["employees_checked"] == 1


def test_minimum_wage_with_no_hourly_staff_is_unknown_not_compliant():
    """No one to compare against is not a clean bill of health."""
    ctx = {"employees": {LOC: [_emp("Cy N", "exempt", 90000.0)]}}
    assert _run(_derive_minimum_wage(
        None, company_id="c", location_id=LOC, row={"numeric_value": 16.5}, ctx=ctx)) is None


def test_minimum_wage_without_a_threshold_cannot_decide():
    ctx = {"employees": {LOC: [_emp("Ada L", "hourly", 15.0)]}}
    assert _run(_derive_minimum_wage(
        None, company_id="c", location_id=LOC, row={"numeric_value": None}, ctx=ctx)) is None


def test_exempt_salary_ignores_hourly_staff():
    """pay_rate is polymorphic on pay_classification — an hourly rate compared
    against an annual threshold would flag every hourly worker as underpaid."""
    ctx = {"employees": {LOC: [_emp("Ada L", "hourly", 20.0)]}}
    assert _run(_derive_exempt_salary(
        None, company_id="c", location_id=LOC, row={"numeric_value": 68640.0}, ctx=ctx)) is None


def test_exempt_salary_flags_a_misclassified_salary():
    ctx = {"employees": {LOC: [_emp("Cy N", "exempt", 50000.0)]}}
    status, ev = _run(_derive_exempt_salary(
        None, company_id="c", location_id=LOC, row={"numeric_value": 68640.0}, ctx=ctx))
    assert status == "non_compliant"
    assert ev["violations"] == 1


def test_training_not_assigned_is_unknown_not_violation():
    """Absence of records is not evidence of an untrained workforce."""
    assert _run(_derive_harassment_training(
        None, company_id="c", location_id=LOC, row={}, ctx={"training": None})) is None
    assert _run(_derive_harassment_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"training": {"assigned": 0, "completed": 0}})) is None


def test_training_partially_complete_is_in_progress():
    status, ev = _run(_derive_harassment_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"training": {"assigned": 10, "completed": 7}}))
    assert status == "in_progress"
    assert (ev["completed"], ev["assigned"]) == (7, 10)


def test_training_fully_complete_is_compliant():
    status, _ = _run(_derive_harassment_training(
        None, company_id="c", location_id=LOC, row={},
        ctx={"training": {"assigned": 10, "completed": 10}}))
    assert status == "compliant"


def test_no_incidents_is_unknown_not_a_working_system():
    assert _run(_derive_injury_recordkeeping(
        None, company_id="c", location_id=LOC, row={}, ctx={"incidents": {}})) is None


def test_unclassified_incidents_are_a_recordkeeping_violation():
    status, ev = _run(_derive_injury_recordkeeping(
        None, company_id="c", location_id=LOC, row={},
        ctx={"incidents": {LOC: {"total": 5, "unclassified": 2}}}))
    assert status == "non_compliant"
    assert ev["unclassified"] == 2


# ── registry integrity ──────────────────────────────────────────────────────

def test_every_wage_derivation_is_feature_gated_on_the_roster():
    """A wage rule with no roster is unknowable — a Lite-Essentials tenant has
    no employees table to compare against and must not be scored."""
    for key in ("state_minimum_wage", "local_minimum_wage", "national_minimum_wage",
                "exempt_salary_threshold"):
        assert DERIVATIONS[key].required_feature == "employees"


def test_gated_derivations_name_a_real_flag():
    from app.core.feature_flags import DEFAULT_COMPANY_FEATURES
    known = set(DEFAULT_COMPANY_FEATURES) | {"employees", "incidents"}
    for d in DERIVATIONS.values():
        if d.required_feature:
            assert d.required_feature in known, f"{d.key} gates on unknown flag {d.required_feature}"


def test_derivation_keys_are_self_consistent():
    for key, d in DERIVATIONS.items():
        assert d.key == key
        assert d.label


def test_derivable_keys_are_real_registry_keys():
    """A derivation keyed on a name the RKD doesn't know can never fire — the
    reconcile query matches on cat.regulation_key."""
    from app.core.services.compliance_evals.industry_keysets import CORE_LABOR_KEYS
    labor = {k for keys in CORE_LABOR_KEYS.values() for k in keys}
    # Not every derivable key is a core labor key, but the wage/training ones are.
    assert "state_minimum_wage" in labor
    assert "exempt_salary_threshold" in labor
    assert "harassment_prevention_training" in labor
    assert set(derivable_keys()) >= {"state_minimum_wage", "exempt_salary_threshold"}


@pytest.mark.parametrize("status", STATUSES)
def test_status_vocabulary_matches_the_migration_check(status):
    """If these drift the INSERT throws at runtime, not at import."""
    assert status in ("compliant", "non_compliant", "in_progress", "unknown")


# ── workforce verdicts (shared by DERIVATIONS + the workforce requirement gate) ──

def test_workforce_domains_are_registered_and_feature_gated():
    for key in ("pay_transparency", "federal_equal_pay", "pay_equity", "state_biometric_privacy_laws"):
        assert key in DERIVATIONS, f"{key} missing from DERIVATIONS"
        assert DERIVATIONS[key].required_feature == "workforce_compliance"


def test_pay_transparency_verdict():
    assert pay_transparency_verdict("compliant")[0] == "compliant"
    assert pay_transparency_verdict("action_needed")[0] == "non_compliant"
    # No tracker row for the state → unknown, never a silent pass.
    assert pay_transparency_verdict(None)[0] == "unknown"
    assert pay_transparency_verdict("na")[0] == "unknown"


def test_pay_equity_verdict():
    assert pay_equity_verdict(None)[0] == "unknown"  # no study on file
    assert pay_equity_verdict({"overdue": True})[0] == "in_progress"
    # Material unremediated gap is a live finding, not compliance.
    assert pay_equity_verdict({"overdue": False, "gap_pct": 10.0, "remediation": None})[0] == "non_compliant"
    # Same gap with remediation underway is not thrown as non-compliant.
    assert pay_equity_verdict({"overdue": False, "gap_pct": 10.0, "remediation": "bands rolling out"})[0] == "compliant"
    # A small gap is within noise.
    assert pay_equity_verdict({"overdue": False, "gap_pct": 2.0, "remediation": None})[0] == "compliant"
    assert pay_equity_verdict({"overdue": False, "gap_pct": None, "remediation": None})[0] == "compliant"


def test_biometrics_verdict():
    assert biometrics_verdict(0, 0)[0] == "unknown"     # nothing registered → blind
    assert biometrics_verdict(3, 1)[0] == "non_compliant"  # a point missing consent
    assert biometrics_verdict(3, 0)[0] == "compliant"


def test_verdict_unknown_maps_to_none_in_derivations():
    """The gate shows 'unknown'; the per-requirement engine must instead go blind
    (None), so a tenant is never told they violate a law we couldn't evaluate."""
    from app.core.services.compliance_status import _verdict_to_derivation
    assert _verdict_to_derivation("unknown", "no data") is None
    assert _verdict_to_derivation("compliant", "ok") == ("compliant", {"rule": "ok"})
