"""Unit tests for the HRIS → business_locations ingest (_sync_company_locations).

Uses a fake asyncpg connection — no DB. Covers the additive-only dedupe,
US-jurisdiction gating (USPS-code whitelist, country filter), incomplete-row
skips, and the no-locations-surface (ADP) no-op.
"""
import asyncio
from uuid import uuid4

from app.matcha.services.hris_sync_orchestrator import _sync_company_locations
from app.matcha.services.hris_service import HRISProvisioningError


class FakeConn:
    """Just enough asyncpg surface for _sync_company_locations."""

    def __init__(self, existing: set[tuple[str, str]] | None = None):
        self.existing = existing or set()  # {(city_lower, STATE)}
        self.inserted: list[dict] = []

    async def fetchval(self, query, company_id, city, state):
        return 1 if (city.lower(), state.upper()) in self.existing else None

    async def execute(self, query, company_id, name, address, city, state, zipcode):
        self.inserted.append(
            {"name": name, "address": address, "city": city, "state": state, "zipcode": zipcode}
        )


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


def _loc(city, state, postal="94105", country="US", line1="1 Main St", name=None):
    return {"name": name, "line1": line1, "line2": None, "city": city,
            "state": state, "postal_code": postal, "country": country}


def _run(service, conn):
    return asyncio.run(
        _sync_company_locations(conn, uuid4(), service, {"mode": "finch"}, {})
    )


class TestSyncCompanyLocations:
    def test_creates_new_locations(self):
        conn = FakeConn()
        created = _run(FakeService([_loc("San Francisco", "CA"), _loc("Austin", "TX", postal="78701")]), conn)
        assert created == 2
        assert {(r["city"], r["state"]) for r in conn.inserted} == {
            ("San Francisco", "CA"), ("Austin", "TX"),
        }

    def test_existing_city_state_never_touched(self):
        # Additive-only: a manual row for the same (city, state) wins.
        conn = FakeConn(existing={("san francisco", "CA")})
        created = _run(FakeService([_loc("San Francisco", "CA")]), conn)
        assert created == 0
        assert conn.inserted == []

    def test_non_usps_region_skipped_even_without_country(self):
        # Canadian province with a null country must not become a US jurisdiction.
        conn = FakeConn()
        created = _run(FakeService([_loc("Toronto", "ON", postal="M5H", country=None)]), conn)
        assert created == 0

    def test_explicit_foreign_country_skipped(self):
        conn = FakeConn()
        created = _run(FakeService([_loc("London", "LD", postal="EC1A", country="GB")]), conn)
        assert created == 0

    def test_incomplete_rows_skipped(self):
        conn = FakeConn()
        created = _run(
            FakeService([
                _loc("", "CA"),                      # no city
                _loc("Fresno", "CA", postal=None),   # no zip
                _loc("Fresno", None),                # no state
            ]),
            conn,
        )
        assert created == 0

    def test_name_defaults_to_city_state(self):
        conn = FakeConn()
        _run(FakeService([_loc("Reno", "NV", postal="89501", name=None)]), conn)
        # normalize_hris_locations usually synthesizes name; the upsert has its
        # own fallback when it's absent.
        assert conn.inserted[0]["name"] == "Reno, NV"

    def test_service_without_locations_surface_is_noop(self):
        conn = FakeConn()
        created = _run(ServiceWithoutLocations(), conn)
        assert created == 0
        assert conn.inserted == []

    def test_provisioning_error_degrades_to_zero(self):
        conn = FakeConn()
        created = _run(
            FakeService(error=HRISProvisioningError("fetch_failed", "boom")), conn
        )
        assert created == 0
