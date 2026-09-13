import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.models.compliance import LocationCreate
from app.core.services.compliance_service import _locations
from app.core.services.location_timezone import (
    SINGLE_ZONE_US_TIMEZONES,
    TimezoneResolutionError,
    infer_location_timezone,
    timezone_for_create,
    timezone_for_update,
)


def test_infers_unambiguous_state_timezone():
    assert infer_location_timezone(state="ca") == "America/Los_Angeles"
    assert infer_location_timezone(state="NY") == "America/New_York"


def test_split_zone_state_requires_manual_selection():
    assert infer_location_timezone(state="FL") is None
    with pytest.raises(TimezoneResolutionError, match="Select the correct time zone manually"):
        timezone_for_create(
            timezone=None,
            timezone_source="auto",
            state="FL",
            country_code="US",
        )


def test_create_preserves_legacy_omission_and_marks_explicit_values():
    legacy = timezone_for_create(
        timezone=None, timezone_source=None, state="CA", country_code="US"
    )
    assert legacy.timezone is None
    assert legacy.source is None

    automatic = timezone_for_create(
        timezone=None, timezone_source="auto", state="CA", country_code="US"
    )
    assert automatic.timezone == "America/Los_Angeles"
    assert automatic.source == "auto"

    manual = timezone_for_create(
        timezone="America/Denver", timezone_source=None, state="CA", country_code="US"
    )
    assert manual.timezone == "America/Denver"
    assert manual.source == "manual"


def test_invalid_manual_timezone_is_rejected():
    with pytest.raises(TimezoneResolutionError, match="valid IANA"):
        timezone_for_create(
            timezone="US/Definitely_Not_A_Zone",
            timezone_source="manual",
            state="CA",
            country_code="US",
        )


def test_auto_edit_re_evaluates_geography_but_manual_override_survives():
    automatic = timezone_for_update(
        timezone=None,
        timezone_was_supplied=False,
        timezone_source=None,
        existing_timezone="America/Los_Angeles",
        existing_source="auto",
        state="CO",
        country_code="US",
        geography_changed=True,
    )
    assert automatic.timezone == "America/Denver"
    assert automatic.source == "auto"

    manual = timezone_for_update(
        timezone=None,
        timezone_was_supplied=False,
        timezone_source=None,
        existing_timezone="America/Los_Angeles",
        existing_source="manual",
        state="CO",
        country_code="US",
        geography_changed=True,
    )
    assert manual.timezone is None
    assert manual.source is None


def test_explicit_auto_switch_and_manual_override():
    automatic = timezone_for_update(
        timezone="America/Chicago",
        timezone_was_supplied=True,
        timezone_source="auto",
        existing_timezone="America/Chicago",
        existing_source="manual",
        state="CA",
        country_code="US",
        geography_changed=False,
    )
    assert automatic.timezone == "America/Los_Angeles"
    assert automatic.source == "auto"

    manual = timezone_for_update(
        timezone="America/Phoenix",
        timezone_was_supplied=True,
        timezone_source="manual",
        existing_timezone="America/Los_Angeles",
        existing_source="auto",
        state="AZ",
        country_code="US",
        geography_changed=True,
    )
    assert manual.timezone == "America/Phoenix"
    assert manual.source == "manual"


def test_explicit_null_update_preserves_existing_timezone_mode():
    unchanged = timezone_for_update(
        timezone=None,
        timezone_was_supplied=True,
        timezone_source=None,
        existing_timezone="America/Los_Angeles",
        existing_source="auto",
        state="CA",
        country_code="US",
        geography_changed=False,
    )

    assert unchanged.timezone is None
    assert unchanged.source is None


def test_legacy_echo_does_not_demote_automatic_timezone():
    unchanged = timezone_for_update(
        timezone="America/Los_Angeles",
        timezone_was_supplied=True,
        timezone_source=None,
        existing_timezone="America/Los_Angeles",
        existing_source="auto",
        state="CA",
        country_code="US",
        geography_changed=False,
    )
    remapped = timezone_for_update(
        timezone="America/Los_Angeles",
        timezone_was_supplied=True,
        timezone_source=None,
        existing_timezone="America/Los_Angeles",
        existing_source="auto",
        state="CO",
        country_code="US",
        geography_changed=True,
    )

    assert unchanged.timezone is None
    assert unchanged.source is None
    assert remapped.timezone == "America/Denver"
    assert remapped.source == "auto"


def test_client_and_server_state_maps_stay_in_sync():
    repo_root = Path(__file__).resolve().parents[3]
    client_source = (
        repo_root / "client/src/utils/locationTimezone.ts"
    ).read_text(encoding="utf-8")
    mapping_source = client_source.split(
        "const SINGLE_ZONE_US_TIMEZONES", 1
    )[1].split("}", 1)[0]
    client_mapping = dict(re.findall(r"\b([A-Z]{2}): '([^']+)'", mapping_source))

    assert client_mapping == SINGLE_ZONE_US_TIMEZONES


@pytest.mark.asyncio
async def test_bootstrap_provides_location_timezone_prerequisites():
    from app.database.bootstrap.compliance import create_compliance

    class RecordingConnection:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, *args):
            self.statements.append(statement)

        async def fetchval(self, *args):
            return 0

    conn = RecordingConnection()
    await create_compliance(conn)
    bootstrap_sql = "\n".join(conn.statements)

    assert "ADD COLUMN IF NOT EXISTS country_code" in bootstrap_sql
    assert "ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)" in bootstrap_sql
    assert "ADD COLUMN IF NOT EXISTS timezone_source" in bootstrap_sql


@pytest.mark.asyncio
async def test_create_location_persists_normalized_country_code(monkeypatch):
    company_id = uuid4()
    location_id = uuid4()
    jurisdiction_id = uuid4()

    class RecordingConnection:
        insert_statement = None
        insert_args = None

        async def fetchval(self, statement, *args):
            assert "INSERT INTO business_locations" in statement
            self.insert_statement = statement
            self.insert_args = args
            return location_id

        async def execute(self, *args):
            return "UPDATE 1"

        async def fetchrow(self, statement, *args):
            assert "SELECT * FROM business_locations" in statement
            now = datetime.now()
            return {
                "id": location_id,
                "company_id": company_id,
                "jurisdiction_id": jurisdiction_id,
                "city": "Mexico City",
                "state": "CM",
                "country_code": "MX",
                "timezone": None,
                "timezone_source": "manual",
                "created_at": now,
                "updated_at": now,
            }

    conn = RecordingConnection()

    @asynccontextmanager
    async def fake_get_connection():
        yield conn

    async def fake_jurisdiction(*args, **kwargs):
        return jurisdiction_id

    async def fake_has_local_ordinance(*args, **kwargs):
        return True

    async def fake_requirements(*args, **kwargs):
        return []

    monkeypatch.setattr("app.database.get_connection", fake_get_connection)
    monkeypatch.setattr(_locations, "_get_or_create_jurisdiction", fake_jurisdiction)
    monkeypatch.setattr(_locations, "_lookup_has_local_ordinance", fake_has_local_ordinance)
    monkeypatch.setattr(_locations, "_load_jurisdiction_requirements", fake_requirements)

    location, has_coverage = await _locations.create_location(
        company_id,
        LocationCreate(city="Mexico City", state="CM", country_code="mx"),
    )

    normalized_insert = " ".join(conn.insert_statement.split())
    assert "zipcode, country_code, facility_attributes" in normalized_insert
    assert conn.insert_args[7] == "MX"
    assert location.country_code == "MX"
    assert has_coverage is False
