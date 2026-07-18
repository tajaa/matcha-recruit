"""Pure Coterie quote-payload mapping — DB-free.

Covers the two things that would silently ship wrong: caller overrides winning
over derived company data (and an unset override NOT clobbering a real value),
and the mock quote scaling with exposure so the bind flow is testable without
live carrier credentials.
"""

from app.matcha.services import coterie_service as cs


_COMPANY = {
    "name": "Acme Widgets",
    "legal_name": "Acme Widgets LLC",
    "naics": "339999",
    "industry": "Manufacturing",
    "headquarters_state": "TX",
}
_LOCATION = {"state": "CA", "zipcode": "94105"}
_EMP = {"headcount": 12, "annual_payroll": 660000.0}


def test_derives_from_company_when_no_overrides():
    p = cs.build_payload("bop", _COMPANY, _LOCATION, _EMP, {})
    assert p["product"] == "BOP"
    # location state wins over HQ state as the primary risk location
    assert p["business"]["state"] == "CA"
    assert p["business"]["zip"] == "94105"
    assert p["business"]["legal_name"] == "Acme Widgets LLC"
    assert p["exposure"]["headcount"] == 12
    assert p["exposure"]["annual_payroll"] == 660000.0


def test_override_wins_over_derived():
    p = cs.build_payload("wc", _COMPANY, _LOCATION, _EMP, {"state": "NY", "headcount": 40})
    assert p["product"] == "WC"
    assert p["business"]["state"] == "NY"
    assert p["exposure"]["headcount"] == 40
    # an override that was NOT sent must not blank the derived value
    assert p["business"]["zip"] == "94105"
    assert p["exposure"]["annual_payroll"] == 660000.0


def test_falls_back_to_company_name_and_hq_state():
    company = {"name": "Solo Shop", "headquarters_state": "OR"}
    p = cs.build_payload("gl", company, None, {}, {})
    assert p["business"]["legal_name"] == "Solo Shop"  # no legal_name → name
    assert p["business"]["state"] == "OR"              # no location → HQ state
    assert p["exposure"]["headcount"] is None


def test_mock_quote_scales_with_exposure():
    small = cs._mock_quote(cs.build_payload("bop", _COMPANY, _LOCATION, {"headcount": 2, "annual_payroll": 90000}, {}))
    big = cs._mock_quote(cs.build_payload("bop", _COMPANY, _LOCATION, {"headcount": 50, "annual_payroll": 3000000}, {}))
    assert small["premium_cents"] < big["premium_cents"]
    assert small["quote_ref"].startswith("MOCK-BOP-")
    assert small["expires_at"]  # a quote has an expiry


def test_line_maps_to_coverage_key():
    # BOP records its GL leg on carried-coverage lines
    assert cs._LINE_TO_COVERAGE["bop"] == "gl"
    assert cs._LINE_TO_COVERAGE["wc"] == "wc"
