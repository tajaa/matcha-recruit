"""Unit tests for `get_wage_floors_for_state` — the grounding source for
Huume's `lookup_context(topic='wage_floors')`. No DB: a FakeConn scripts
`.fetch()` by inspecting the query text, since the function issues up to
three distinct queries (company-codified, catalog city-level, catalog
state-level) and precedence between them is exactly what's under test.

    cd server && ./venv/bin/python -m pytest tests/compliance/test_wage_floors.py -q
"""

import asyncio
from uuid import uuid4

from app.core.services import compliance_service as cs

COMPANY_ID = uuid4()


class FakeConn:
    """Just enough asyncpg surface for get_wage_floors_for_state. Branches
    on distinctive substrings in the query text to return the right fixture
    for each of the three tiers."""

    def __init__(self, *, company_rows=None, city_rows=None, state_rows=None):
        self.company_rows = company_rows or []
        self.city_rows = city_rows or []
        self.state_rows = state_rows or []
        self.queries: list[str] = []

    async def fetch(self, query, *args):
        self.queries.append(query)
        if "compliance_requirements cr" in query:
            return self.company_rows
        if "FROM jurisdictions j" in query:
            return self.state_rows
        if "jurisdiction_requirements jr" in query:
            return self.city_rows
        raise AssertionError(f"unexpected query: {query}")


def _run(coro):
    return asyncio.run(coro)


def _row(rate_type, numeric_value):
    return {"rate_type": rate_type, "numeric_value": numeric_value}


def _city_row(rate_type, numeric_value, level="city"):
    return {"rate_type": rate_type, "numeric_value": numeric_value, "jurisdiction_level": level}


class TestPrecedence:
    def test_company_codified_wins_over_catalog(self):
        # All three rate types satisfied by company rows, so neither
        # fallback tier's query should even run.
        conn = FakeConn(
            company_rows=[_row("exempt_salary", 71000.0), _row("general", 17.0), _row("tipped", 15.0)],
            state_rows=[_row("exempt_salary", 70304.0)],
        )
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "ca"))
        assert result["found"] is True
        assert result["floors"]["exempt_salary"]["value"] == 71000.0
        assert result["floors"]["exempt_salary"]["source"] == "company_codified"
        # Precedence check: the state-level catalog query must never even
        # run once the company-codified rows already satisfied every rate type.
        assert not any("FROM jurisdictions j" in q for q in conn.queries)
        assert not any("jurisdiction_requirements jr" in q and "compliance_requirements" not in q for q in conn.queries)

    def test_falls_back_to_catalog_city_when_company_has_nothing(self):
        conn = FakeConn(
            company_rows=[],
            city_rows=[_city_row("exempt_salary", 70304.0)],
            state_rows=[_row("exempt_salary", 65000.0)],  # would be wrong if picked
        )
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "CA"))
        assert result["floors"]["exempt_salary"]["value"] == 70304.0
        assert result["floors"]["exempt_salary"]["source"] == "catalog_city"

    def test_catalog_city_row_labeled_catalog_state_when_fk_points_at_state_row(self):
        # bl.jurisdiction_id can point at a state-level jurisdictions row —
        # the source label must reflect the row that actually won, not be
        # hardcoded to "catalog_city".
        conn = FakeConn(
            company_rows=[],
            city_rows=[_city_row("exempt_salary", 65000.0, level="state")],
        )
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "CA"))
        assert result["floors"]["exempt_salary"]["source"] == "catalog_state"

    def test_multiple_locations_same_tier_takes_the_max(self):
        # A company with e.g. SF + Fresno locations gets two city-level
        # `general` rows back — the query orders by numeric_value DESC
        # within a tier (simulated here by fixture order, since FakeConn
        # doesn't sort), so the higher one wins and a company-wide answer
        # is never below the legal floor at any one location.
        conn = FakeConn(
            company_rows=[],
            city_rows=[_city_row("general", 18.07), _city_row("general", 16.50)],
        )
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "CA"))
        assert result["floors"]["general"]["value"] == 18.07

    def test_falls_back_to_catalog_state_when_nothing_else_matches(self):
        conn = FakeConn(company_rows=[], city_rows=[], state_rows=[_row("exempt_salary", 70304.0)])
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "CA"))
        assert result["floors"]["exempt_salary"]["value"] == 70304.0
        assert result["floors"]["exempt_salary"]["source"] == "catalog_state"

    def test_per_rate_type_precedence_is_independent(self):
        # Company has codified `general` but not `exempt_salary` — the
        # exempt figure must still fall through to the catalog rather than
        # the whole lookup bailing once ANY rate type is satisfied.
        conn = FakeConn(
            company_rows=[_row("general", 16.90)],
            state_rows=[_row("exempt_salary", 70304.0)],
        )
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "CA"))
        assert result["floors"]["general"]["source"] == "company_codified"
        assert result["floors"]["exempt_salary"]["source"] == "catalog_state"

    def test_nothing_found_anywhere_is_explicit(self):
        conn = FakeConn()
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "CA"))
        assert result == {"state": "CA", "found": False, "floors": {}}


class TestUnitsAndShape:
    def test_exempt_salary_is_annual_general_is_hourly(self):
        conn = FakeConn(state_rows=[_row("exempt_salary", 70304.0), _row("general", 16.90)])
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "CA"))
        assert result["floors"]["exempt_salary"]["unit"] == "annual"
        assert result["floors"]["general"]["unit"] == "hourly"

    def test_state_normalized_to_upper(self):
        conn = FakeConn(state_rows=[_row("general", 16.90)])
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "ca"))
        assert result["state"] == "CA"


class TestBadInput:
    def test_non_two_letter_state_short_circuits_without_query(self):
        conn = FakeConn()
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, "California"))
        assert result == {"state": "CALIFORNIA", "found": False, "floors": {}}
        assert conn.queries == []

    def test_empty_state_short_circuits(self):
        conn = FakeConn()
        result = _run(cs.get_wage_floors_for_state(conn, COMPANY_ID, ""))
        assert result["found"] is False
        assert conn.queries == []
