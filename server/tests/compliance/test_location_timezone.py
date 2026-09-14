import pytest

from app.core.services.location_timezone import (
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
