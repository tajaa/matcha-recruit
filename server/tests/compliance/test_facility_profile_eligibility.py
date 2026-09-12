import pytest

import app.core.services.compliance_service._locations as locations_module
from app.core.services.compliance_service._locations import (
    _facility_profile_eligible,
)


def test_hospitality_location_naics_suppresses_healthcare_profile_prompt():
    assert not _facility_profile_eligible("722515", None, "Healthcare", ["oncology"])


def test_healthcare_location_naics_enables_profile_prompt():
    assert _facility_profile_eligible(
        "621210", None, "Restaurant / Hospitality", None
    )


def test_company_naics_is_used_when_location_naics_is_missing():
    assert _facility_profile_eligible(None, "621111", "Hospitality", None)
    assert not _facility_profile_eligible(None, "722513", "Healthcare", ["oncology"])


def test_company_industry_is_used_only_when_naics_is_missing():
    assert _facility_profile_eligible(None, None, "Dental Practice", None)
    assert not _facility_profile_eligible(None, None, "Cafe / Restaurant", None)


def test_unmodeled_location_naics_falls_back_to_company_naics():
    assert _facility_profile_eligible("N/A", "621111", "Hospitality", None)
    assert not _facility_profile_eligible("N/A", "722513", "Healthcare", None)


def test_unmodeled_naics_values_fall_back_to_company_industry():
    assert _facility_profile_eligible("N/A", "unknown", "Healthcare", None)


def test_biotech_industry_is_eligible_without_naics():
    assert _facility_profile_eligible(None, None, "biotech", None)


def test_healthcare_specialties_make_unmodeled_industry_eligible():
    assert _facility_profile_eligible(None, None, "other", ["primary_care"])
    assert not _facility_profile_eligible(None, None, "other", [])


@pytest.mark.asyncio
async def test_get_locations_uses_company_specialties_without_leaking_query_fields(
    monkeypatch,
):
    class FakeConnection:
        query = ""

        async def fetch(self, query, _company_id):
            self.query = query
            return [
                {
                    "id": "location-id",
                    "company_id": "company-id",
                    "naics": "N/A",
                    "company_naics": None,
                    "company_industry": "other",
                    "company_healthcare_specialties": ["primary_care"],
                    "projected_count": 0,
                    "jurisdiction_repo_count": 0,
                }
            ]

    class ConnectionContext:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, *_args):
            return None

    async def fake_codified_gate_sql(*_args, **_kwargs):
        return ""

    conn = FakeConnection()
    monkeypatch.setattr(
        "app.database.get_connection", lambda: ConnectionContext(conn)
    )
    monkeypatch.setattr(
        locations_module, "codified_gate_sql", fake_codified_gate_sql
    )

    locations = await locations_module.get_locations("company-id")

    assert "c.healthcare_specialties AS company_healthcare_specialties" in conn.query
    assert locations[0]["facility_profile_eligible"] is True
    assert "company_naics" not in locations[0]
    assert "company_industry" not in locations[0]
    assert "company_healthcare_specialties" not in locations[0]
