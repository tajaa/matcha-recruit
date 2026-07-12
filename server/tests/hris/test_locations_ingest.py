"""Unit tests for the HRIS → business_locations ingest.

Two units, no DB:

- ``_fetch_company_locations`` — best-effort provider fetch (no locations surface
  on ADP, provider errors) that runs *outside* the import connection.
- ``_sync_company_locations`` — the ingest itself. Grounds every location through
  ``ensure_location_for_employee`` (the helper that resolves the county and links
  the ``jurisdiction_id``); a raw INSERT would leave the row invisible to the
  compliance engine while still suppressing the roster build that would have
  grounded it. The helper is stubbed here — its own behavior is compliance_service's
  to test; what matters is that the ingest routes through it and never hand-rolls
  an INSERT.
"""
import asyncio
from uuid import UUID, uuid4

import pytest

import app.core.services.compliance_service as compliance_service
from app.matcha.services.hris_service import HRISProvisioningError
from app.matcha.services.hris_sync_orchestrator import (
    _fetch_company_locations,
    _sync_company_locations,
)


class FakeConn:
    """Just enough asyncpg surface for _sync_company_locations."""

    def __init__(self, existing: set[tuple[str, str]] | None = None):
        self.existing = existing or set()  # {(city_lower, STATE)}
        self.updates: list[dict] = []

    async def fetchval(self, query, company_id, city, state):
        return 1 if (city.lower(), state.upper()) in self.existing else None

    async def execute(self, query, location_id, name, address):
        self.updates.append({"id": location_id, "name": name, "address": address})


class FakeService:
    def __init__(self, locations=None, error: Exception | None = None):
        self._locations = locations or []
        self._error = error

    async def fetch_locations(self, config, secrets):
        if self._error:
            raise self._error
        return self._locations


class ServiceWithoutLocations:
    """Mimics the ADP HRISService — no fetch_locations attribute."""


@pytest.fixture
def grounded(monkeypatch):
    """Stub ensure_location_for_employee; record every call it receives.

    Patched on the compliance_service module because the orchestrator imports it
    lazily inside the function body (cycle avoidance), so the lookup happens at
    call time.
    """
    calls: list[dict] = []

    async def fake_ensure(conn, company_id, work_city, work_state, background_tasks=None, work_zip=None):
        calls.append({"city": work_city, "state": work_state, "zip": work_zip})
        return uuid4()

    monkeypatch.setattr(compliance_service, "ensure_location_for_employee", fake_ensure)
    return calls


def _loc(city, state, postal="94105", country="US", line1="1 Main St", name=None):
    return {"name": name, "line1": line1, "line2": None, "city": city,
            "state": state, "postal_code": postal, "country": country}


def _run(locations, conn):
    return asyncio.run(_sync_company_locations(conn, uuid4(), locations))


class TestSyncCompanyLocations:
    def test_creates_new_locations_through_the_grounding_helper(self, grounded):
        conn = FakeConn()
        created = _run([_loc("San Francisco", "CA"), _loc("Austin", "TX", postal="78701")], conn)
        assert created == 2
        # Every location is grounded (county + jurisdiction_id) rather than raw-INSERTed.
        assert [(c["city"], c["state"], c["zip"]) for c in grounded] == [
            ("San Francisco", "CA", "94105"), ("Austin", "TX", "78701"),
        ]

    def test_hris_name_and_address_carried_onto_new_rows(self, grounded):
        # The helper names a fresh row "City, ST" with an empty address; the ingest
        # patches the HRIS label/street on top.
        conn = FakeConn()
        _run([_loc("Reno", "NV", postal="89501", name="Reno Depot", line1="9 Vine St")], conn)
        assert conn.updates[0]["name"] == "Reno Depot"
        assert conn.updates[0]["address"] == "9 Vine St"
        assert isinstance(conn.updates[0]["id"], UUID)

    def test_existing_row_is_not_renamed_or_recounted(self, grounded):
        # Additive: a manual row for the same (city, state) keeps its own name/address.
        conn = FakeConn(existing={("san francisco", "CA")})
        created = _run([_loc("San Francisco", "CA", name="HRIS Name")], conn)
        assert created == 0
        assert conn.updates == []
        # Still routed through the helper — it dedupes to the same row (and would
        # reactivate it if the company had deactivated it).
        assert len(grounded) == 1

    def test_non_usps_region_skipped_even_without_country(self, grounded):
        # Canadian province with a null country must not become a US jurisdiction.
        conn = FakeConn()
        created = _run([_loc("Toronto", "ON", postal="M5H", country=None)], conn)
        assert created == 0
        assert grounded == []

    def test_explicit_foreign_country_skipped(self, grounded):
        conn = FakeConn()
        created = _run([_loc("London", "LD", postal="EC1A", country="GB")], conn)
        assert created == 0
        assert grounded == []

    def test_incomplete_rows_skipped(self, grounded):
        conn = FakeConn()
        created = _run(
            [
                _loc("", "CA"),                      # no city
                _loc("Fresno", "CA", postal=None),   # no zip
                _loc("Fresno", None),                # no state
            ],
            conn,
        )
        assert created == 0
        assert grounded == []

    def test_lowercase_state_is_accepted(self, grounded):
        conn = FakeConn()
        created = _run([_loc("Austin", "tx", postal="78701")], conn)
        assert created == 1
        assert grounded[0]["state"] == "TX"

    def test_empty_locations_is_a_noop(self, grounded):
        conn = FakeConn()
        assert _run([], conn) == 0
        assert grounded == []


class TestFetchCompanyLocations:
    def test_returns_provider_locations(self):
        locs = asyncio.run(
            _fetch_company_locations(FakeService([_loc("Reno", "NV")]), {}, {}, uuid4())
        )
        assert locs[0]["city"] == "Reno"

    def test_service_without_locations_surface_is_noop(self):
        locs = asyncio.run(
            _fetch_company_locations(ServiceWithoutLocations(), {}, {}, uuid4())
        )
        assert locs == []

    def test_provisioning_error_degrades_to_empty(self):
        svc = FakeService(error=HRISProvisioningError("fetch_failed", "boom"))
        assert asyncio.run(_fetch_company_locations(svc, {}, {}, uuid4())) == []

    def test_unexpected_error_degrades_to_empty(self):
        # Location ingest is additive/best-effort — it never fails the sync.
        svc = FakeService(error=RuntimeError("provider exploded"))
        assert asyncio.run(_fetch_company_locations(svc, {}, {}, uuid4())) == []
