"""Jurisdiction-chain resolution for location-scoped coverage.

Coverage for an establishment is the union of city ∪ county ∪ state ∪ federal:
a requirement recorded at the state level covers a business in the city, so
counting only the city row would report nearly everything as missing.
"""
import pytest

from app.core.routes.admin import _resolve_jurisdiction_chain

FEDERAL = "fed-id"
CA = "ca-id"
LA_CITY = "la-city-id"
LA_COUNTY = "la-county-id"


class FakeConn:
    """Answers the three queries `_resolve_jurisdiction_chain` issues."""

    def __init__(self, *, federal=FEDERAL, states=None, cities=None, counties=None):
        self.federal = federal
        self.states = states or {}
        self.cities = cities or {}
        self.counties = counties or {}

    async def fetchval(self, sql, *args):
        if "level::text = 'federal'" in sql:
            return self.federal
        if "level::text = 'state'" in sql:
            return self.states.get(args[0])
        if "level::text = 'county'" in sql:
            return self.counties.get((args[0].lower(), args[1]))
        raise AssertionError(f"unexpected fetchval: {sql}")

    async def fetchrow(self, sql, *args):
        assert "LOWER(city)" in sql
        return self.cities.get((args[0].lower(), args[1]))


@pytest.mark.asyncio
async def test_full_chain_city_county_state_federal():
    conn = FakeConn(
        states={"CA": CA},
        cities={("los angeles", "CA"): {"id": LA_CITY, "county": "Los Angeles"}},
        counties={("los angeles", "CA"): LA_COUNTY},
    )
    chain = await _resolve_jurisdiction_chain(conn, "CA", "Los Angeles")
    assert chain["ids"] == [FEDERAL, CA, LA_CITY, LA_COUNTY]
    assert chain["state_found"] and chain["city_found"]


@pytest.mark.asyncio
async def test_state_only_chain():
    conn = FakeConn(states={"CA": CA})
    chain = await _resolve_jurisdiction_chain(conn, "CA", None)
    assert chain["ids"] == [FEDERAL, CA]
    assert chain["state_found"]
    assert chain["city_found"] is False


@pytest.mark.asyncio
async def test_unknown_state_is_detectable_even_though_federal_resolves():
    """Regression: the caller used to 404 on `not ids`, but the federal row always
    resolves — so a nonexistent state looked like a valid one-link chain and its
    coverage was reported as federal-only rather than as an error."""
    conn = FakeConn(states={})
    chain = await _resolve_jurisdiction_chain(conn, "ZZ", None)
    assert chain["ids"] == [FEDERAL]
    assert chain["state_found"] is False


@pytest.mark.asyncio
async def test_unknown_city_degrades_to_state_and_reports_it():
    """Not an error: coverage falls back to state ∪ federal, and the caller is told,
    rather than being shown state coverage as though it were the city's."""
    conn = FakeConn(states={"CA": CA}, cities={})
    chain = await _resolve_jurisdiction_chain(conn, "CA", "Nowheresville")
    assert chain["ids"] == [FEDERAL, CA]
    assert chain["state_found"] is True
    assert chain["city_found"] is False


@pytest.mark.asyncio
async def test_city_without_a_county_row_still_chains():
    """New York City has no county jurisdiction row in dev."""
    conn = FakeConn(
        states={"NY": "ny-id"},
        cities={("new york city", "NY"): {"id": "nyc-id", "county": None}},
    )
    chain = await _resolve_jurisdiction_chain(conn, "NY", "New York City")
    assert chain["ids"] == [FEDERAL, "ny-id", "nyc-id"]
    assert chain["city_found"] is True


@pytest.mark.asyncio
async def test_city_names_county_but_county_row_is_absent():
    conn = FakeConn(
        states={"CA": CA},
        cities={("malibu", "CA"): {"id": "malibu-id", "county": "Los Angeles"}},
        counties={},
    )
    chain = await _resolve_jurisdiction_chain(conn, "CA", "Malibu")
    assert chain["ids"] == [FEDERAL, CA, "malibu-id"]


@pytest.mark.asyncio
async def test_missing_federal_row_does_not_break_the_chain():
    conn = FakeConn(federal=None, states={"CA": CA})
    chain = await _resolve_jurisdiction_chain(conn, "CA", None)
    assert chain["ids"] == [CA]
