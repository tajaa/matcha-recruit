"""Anti-polymorphy check — find_duplicate_obligations (pure, no DB).

One (jurisdiction, category, regulation_key) = one active row. Two rows sharing a
key are either a true duplicate or a key collision (two obligations wearing one
tag); both break codification's isomorphy and must surface as critical findings.
Entity-type variants are the one legitimate split.
"""
from app.core.services.compliance_evals.tagging import find_duplicate_obligations


def _row(id, key, jid="J1", category="cobra", title="t", aet=None):
    return {"id": id, "jurisdiction_id": jid, "category": category,
            "regulation_key": key, "title": title,
            "applicable_entity_types": aet or []}


def test_two_rows_one_key_is_critical():
    # the real dev case: Cal-COBRA and Federal COBRA both keyed cobra_continuation
    findings = find_duplicate_obligations([
        _row("r1", "cobra_continuation", title="Cal-COBRA Continuation Coverage"),
        _row("r2", "cobra_continuation", title="Federal COBRA Continuation Coverage"),
    ])
    assert len(findings) == 1
    f = findings[0]
    assert f["finding_type"] == "duplicate_active_obligation"
    assert f["severity"] == "critical"
    assert f["observed"]["active_rows"] == 2
    assert set(f["observed"]["row_ids"]) == {"r1", "r2"}


def test_unique_keys_no_findings():
    findings = find_duplicate_obligations([
        _row("r1", "cobra_continuation"),
        _row("r2", "fmla", category="leave"),
    ])
    assert findings == []


def test_same_key_different_jurisdictions_ok():
    # federal + CA each having cobra_continuation is the inheritance model, not a dupe
    findings = find_duplicate_obligations([
        _row("r1", "cobra_continuation", jid="FED"),
        _row("r2", "cobra_continuation", jid="CA"),
    ])
    assert findings == []


def test_entity_type_variants_are_a_legitimate_split():
    findings = find_duplicate_obligations([
        _row("r1", "state_facility_licensure", aet=["fqhc"]),
        _row("r2", "state_facility_licensure", aet=["behavioral_health"]),
    ])
    assert findings == []


def test_same_key_different_category_is_two_groups():
    # exempt_salary_threshold under minimum_wage AND overtime = distinct groups
    # (the RKD category guard treats them as different bindings)
    findings = find_duplicate_obligations([
        _row("r1", "exempt_salary_threshold", category="minimum_wage"),
        _row("r2", "exempt_salary_threshold", category="overtime"),
    ])
    assert findings == []


def test_null_key_rows_ignored():
    findings = find_duplicate_obligations([
        _row("r1", None), _row("r2", None),
    ])
    assert findings == []
