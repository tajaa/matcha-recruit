from app.core.services.compliance_service._locations import (
    _facility_profile_eligible,
)


def test_hospitality_location_naics_suppresses_healthcare_profile_prompt():
    assert not _facility_profile_eligible("722515", None, "Healthcare")


def test_healthcare_location_naics_enables_profile_prompt():
    assert _facility_profile_eligible("621210", None, "Restaurant / Hospitality")


def test_company_naics_is_used_when_location_naics_is_missing():
    assert _facility_profile_eligible(None, "621111", "Hospitality")
    assert not _facility_profile_eligible(None, "722513", "Healthcare")


def test_company_industry_is_used_only_when_naics_is_missing():
    assert _facility_profile_eligible(None, None, "Dental Practice")
    assert not _facility_profile_eligible(None, None, "Cafe / Restaurant")


def test_present_unmodeled_location_naics_fails_closed():
    assert not _facility_profile_eligible("not-a-naics", "621111", "Healthcare")
