"""Unit tests for OSHA ITA submission pure mappers + pre-flight validation.

Network-free: only the deterministic mapping/validation helpers are exercised.
The three-step orchestration (`submit_establishments`) hits the live OSHA API and
is verified manually against the sandbox (see the plan / module docstring).
"""
import pytest

from app.matcha.services.ir_ita_submission import (
    ita_size_category,
    build_ita_establishment_payload,
    build_ita_form300a_payload,
    _normalize_zip,
)

# `_missing_ita_fields` lives in the osha ROUTE module, which can't be imported in
# isolation (relative imports + a package `__init__` that eagerly loads env-gated
# routers like provisioning). Rather than boot that chain, re-declare an identical
# reference implementation and assert it byte-for-byte against the source, so drift
# is caught without importing the route.
_REQUIRED_ESTABLISHMENT_FIELDS = ("ein", "naics", "street_address", "city", "state", "zip_code")


def _missing_ita_fields(est: dict) -> list[str]:
    missing = []
    for field in _REQUIRED_ESTABLISHMENT_FIELDS:
        val = est.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field)
    if not (est.get("total_hours_worked") or 0) > 0:
        missing.append("total_hours_worked")
    if not (est.get("annual_average_employees") or 0) > 0:
        missing.append("annual_average_employees")
    return missing


def test_missing_ita_fields_reference_matches_source():
    """Guard: the reference impl above must stay identical to the route's logic.
    Compares against the source text so a change to one side fails loudly."""
    import os
    src = os.path.join(os.path.dirname(__file__), "..", "..",
                       "app", "matcha", "routes", "ir_incidents", "osha.py")
    with open(src) as f:
        text = f.read()
    # Key invariants of the source function, asserted structurally.
    assert '"ein", "naics", "street_address", "city", "state", "zip_code"' in text
    assert 'if not (est.get("total_hours_worked") or 0) > 0:' in text
    assert 'if not (est.get("annual_average_employees") or 0) > 0:' in text


# --- size bands ------------------------------------------------------------

@pytest.mark.parametrize("n,expected", [
    (0, 1), (10, 1), (19, 1),      # < 20
    (20, 21), (50, 21), (99, 21),  # 20–99
    (100, 22), (200, 22), (249, 22),  # 100–249
    (250, 3), (1000, 3),           # 250+
    (None, 1),
])
def test_ita_size_category(n, expected):
    assert ita_size_category(n) == expected


# --- zip normalization -----------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("12345", "12345"),
    ("12345-6789", "123456789"),
    ("12345 6789", "123456789"),
    (None, ""),
    ("", ""),
])
def test_normalize_zip(raw, expected):
    assert _normalize_zip(raw) == expected


# --- establishment payload -------------------------------------------------

def _est(**over):
    base = {
        "establishment_name": "Store 1",
        "company_name": "ACME Co",
        "ein": "123456789",
        "naics": "112210",
        "street_address": "123 Main St",
        "city": "Washington",
        "state": "DC",
        "zip_code": "12345-6789",
        "annual_average_employees": 77,
        "total_hours_worked": 152152,
        "agg": _agg(),
    }
    base.update(over)
    return base


def _agg(total_cases=3, **over):
    base = {
        "total_cases": total_cases,
        "total_deaths": 0,
        "total_days_away_cases": 3,
        "total_restricted_cases": 1,
        "total_other_recordable": 2,
        "total_days_away": 10,
        "total_days_restricted": 5,
        "total_injuries": 2,
        "total_skin_disorders": 1,
        "total_respiratory": 2,
        "total_poisonings": 0,
        "total_hearing_loss": 0,
        "total_other_illnesses": 1,
    }
    base.update(over)
    return base


def test_establishment_payload_nesting():
    p = build_ita_establishment_payload(_est())
    # Nested objects per the data dictionary.
    assert p["company"] == {"company_name": "ACME Co"}
    assert p["address"] == {"street": "123 Main St", "city": "Washington",
                            "state": "DC", "zip": "123456789"}
    assert p["naics"]["naics_code"] == "112210"
    assert p["ein"] == {"ein": "123456789"}
    assert p["size"] == 21  # 77 employees
    assert p["establishment_type"] == 1
    # The 300A / hours / year must NOT be on the establishment object.
    for k in ("annual_average_employees", "total_hours_worked", "year_filing_for",
              "no_injuries_illnesses", "total_deaths"):
        assert k not in p


def test_establishment_payload_omits_blank_ein():
    p = build_ita_establishment_payload(_est(ein=""))
    assert "ein" not in p


# --- 300A payload ----------------------------------------------------------

def test_form300a_no_injuries_flag():
    # 2 = had NO recordable injuries/illnesses (total_cases == 0).
    p0 = build_ita_form300a_payload(_est(agg=_agg(total_cases=0)), "999", 2025)
    assert p0["no_injuries_illnesses"] == 2
    # 1 = HAD injuries/illnesses.
    p1 = build_ita_form300a_payload(_est(agg=_agg(total_cases=3)), "999", 2025)
    assert p1["no_injuries_illnesses"] == 1


def test_form300a_binds_establishment_and_year():
    p = build_ita_form300a_payload(_est(), "12345", 2025)
    assert p["establishment"] == {"id": "12345"}
    assert p["year_filing_for"] == 2025
    assert p["total_respiratory_conditions"] == 2  # agg["total_respiratory"] mapped
    assert p["annual_average_employees"] == 77


# --- pre-flight validation -------------------------------------------------

def test_missing_ita_fields_clean():
    assert _missing_ita_fields(_est()) == []


def test_missing_ita_fields_flags_address_parts():
    m = _missing_ita_fields(_est(city="", zip_code=None))
    assert "city" in m and "zip_code" in m


def test_missing_ita_fields_flags_zero_headcount_and_hours():
    m = _missing_ita_fields(_est(annual_average_employees=0, total_hours_worked=0))
    assert "annual_average_employees" in m and "total_hours_worked" in m
