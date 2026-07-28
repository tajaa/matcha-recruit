"""Unit tests for OSHA ITA submission pure mappers + pre-flight validation.

Network-free: only the deterministic mapping/validation helpers are exercised.
The three-step orchestration (`submit_establishments`) hits the live OSHA API and
is verified manually against the sandbox (see the plan / module docstring).
"""
import pytest

from app.matcha.services.ir.ir_ita_submission import (
    ita_size_category,
    build_ita_establishment_payload,
    build_ita_form300a_payload,
    _normalize_zip,
    _form300a_links,
    _result_errors,
    _stored_form_year,
)

# `_missing_ita_fields` is imported from the REAL route package, not re-declared.
# This file used to carry a local "reference implementation" plus a guard that
# compared it to the source text — but the guard only asserted 3 substrings, so
# when the real function grew `ein_invalid` / `zip_code_invalid` checks the copy
# silently fell behind and every test below was exercising dead code. The comment
# justifying the copy ("the route module can't be imported in isolation") was
# already false: the guard itself imported it.
from app.matcha.routes.ir_incidents.osha import _missing_ita_fields


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


# --- response-shape helpers (verified against the live sandbox) -------------

def test_form300a_links_reads_snake_case():
    # OSHA returns `form300a_links` (snake); the camel variant is tolerated too.
    obj = {"links": {"form300a_links": ["/oshaApi/v1/forms/form300A/2270100"]}}
    assert _form300a_links(obj) == ["/oshaApi/v1/forms/form300A/2270100"]
    assert _form300a_links({"links": {"form300ALinks": ["/x/1"]}}) == ["/x/1"]
    assert _form300a_links({"links": {}}) == []
    assert _form300a_links({}) == []


def test_result_errors_extracts_per_item_errors():
    # /submissions wraps per-item failures in `errors` with no `id`.
    assert _result_errors({"errors": ["No 300A form record was filed for this establishment"]}) == \
        ["No 300A form record was filed for this establishment"]
    assert _result_errors({"id": "123"}) == []
    assert _result_errors({}) == []


def test_stored_form_year_reads_back_osha_year():
    # OSHA may override year_filing_for to the open collection year — read it back.
    body = {"results": [{"id": 2270100, "year_filing_for": 2025}]}
    assert _stored_form_year(body, fallback=2024) == 2025
    # No year in the body → fall back to the requested year.
    assert _stored_form_year({"results": [{"id": 1}]}, fallback=2024) == 2024
    assert _stored_form_year({}, fallback=2023) == 2023


# --- present-but-malformed EIN / zip ---------------------------------------
# These were unreachable while this file re-declared its own _missing_ita_fields:
# the copy predated the ein_invalid / zip_code_invalid checks and the drift guard
# didn't assert on them, so the real validators had no coverage at all.

def test_missing_ita_fields_flags_malformed_ein():
    m = _missing_ita_fields(_est(ein="12345"))
    assert "ein_invalid" in m
    assert "ein" not in m  # present, just wrong — a different filer-facing message


def test_missing_ita_fields_accepts_punctuated_ein():
    assert _missing_ita_fields(_est(ein="12-3456789")) == []


def test_missing_ita_fields_flags_malformed_zip():
    m = _missing_ita_fields(_est(zip_code="123"))
    assert "zip_code_invalid" in m
    assert "zip_code" not in m


@pytest.mark.parametrize("zip_raw", ["12345", "12345-6789", "12345 6789"])
def test_missing_ita_fields_accepts_valid_zip_shapes(zip_raw):
    assert _missing_ita_fields(_est(zip_code=zip_raw)) == []


def test_absent_field_reported_once_not_also_as_invalid():
    # A missing value must not produce BOTH "zip_code" and "zip_code_invalid" —
    # the checklist would show the same gap twice.
    m = _missing_ita_fields(_est(zip_code=None, ein=None))
    assert m.count("zip_code") == 1 and "zip_code_invalid" not in m
    assert m.count("ein") == 1 and "ein_invalid" not in m
