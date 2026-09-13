"""Deterministic timezone handling for physical business locations.

State-only inference is intentionally limited to jurisdictions with one
unambiguous civil timezone.  Split-zone states (and states with local
exceptions) return ``None`` so the caller can require an explicit correction
instead of silently storing a plausible-but-wrong timezone.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SINGLE_ZONE_US_TIMEZONES = {
    "AL": "America/Chicago",
    "AR": "America/Chicago",
    "CA": "America/Los_Angeles",
    "CO": "America/Denver",
    "CT": "America/New_York",
    "DC": "America/New_York",
    "DE": "America/New_York",
    "GA": "America/New_York",
    "GU": "Pacific/Guam",
    "HI": "Pacific/Honolulu",
    "IA": "America/Chicago",
    "IL": "America/Chicago",
    "LA": "America/Chicago",
    "MA": "America/New_York",
    "MD": "America/New_York",
    "ME": "America/New_York",
    "MN": "America/Chicago",
    "MO": "America/Chicago",
    "MP": "Pacific/Saipan",
    "MS": "America/Chicago",
    "MT": "America/Denver",
    "NC": "America/New_York",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NM": "America/Denver",
    "NY": "America/New_York",
    "OH": "America/New_York",
    "OK": "America/Chicago",
    "PA": "America/New_York",
    "PR": "America/Puerto_Rico",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "UT": "America/Denver",
    "VA": "America/New_York",
    "VI": "America/St_Thomas",
    "VT": "America/New_York",
    "WA": "America/Los_Angeles",
    "WI": "America/Chicago",
    "WV": "America/New_York",
    "WY": "America/Denver",
    "AS": "Pacific/Pago_Pago",
}


class TimezoneResolutionError(ValueError):
    """The requested timezone mode cannot safely produce a stored value."""


@dataclass(frozen=True)
class TimezoneWrite:
    timezone: str | None
    source: str | None


def infer_location_timezone(*, state: str | None, country_code: str = "US") -> str | None:
    if country_code.strip().upper() != "US" or not state:
        return None
    return SINGLE_ZONE_US_TIMEZONES.get(state.strip().upper())


def _valid_iana_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _manual_timezone(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise TimezoneResolutionError("Select a time zone manually to continue.")
    if not _valid_iana_timezone(normalized):
        raise TimezoneResolutionError("Select a valid IANA time zone, such as America/Los_Angeles.")
    return normalized


def _auto_timezone(*, state: str | None, country_code: str) -> str:
    inferred = infer_location_timezone(state=state, country_code=country_code)
    if inferred is None:
        raise TimezoneResolutionError(
            "We couldn't map this location to one time zone automatically. "
            "Select the correct time zone manually to continue."
        )
    return inferred


def timezone_for_create(
    *,
    timezone: str | None,
    timezone_source: str | None,
    state: str | None,
    country_code: str,
) -> TimezoneWrite:
    """Resolve an opted-in create while preserving legacy callers that omit both fields."""
    if timezone_source == "auto":
        return TimezoneWrite(_auto_timezone(state=state, country_code=country_code), "auto")
    if timezone_source == "manual":
        return TimezoneWrite(_manual_timezone(timezone), "manual")
    if timezone:
        # Backward-compatible clients historically sent only ``timezone``.
        return TimezoneWrite(_manual_timezone(timezone), "manual")
    return TimezoneWrite(None, None)


def timezone_for_update(
    *,
    timezone: str | None,
    timezone_was_supplied: bool,
    timezone_source: str | None,
    existing_timezone: str | None,
    existing_source: str,
    state: str | None,
    country_code: str,
    geography_changed: bool,
) -> TimezoneWrite:
    """Return only timezone fields that should be included in an UPDATE."""
    if timezone_source == "auto":
        return TimezoneWrite(_auto_timezone(state=state, country_code=country_code), "auto")
    if timezone_source == "manual":
        chosen = timezone if timezone_was_supplied else existing_timezone
        return TimezoneWrite(_manual_timezone(chosen), "manual")
    if timezone_was_supplied:
        return TimezoneWrite(_manual_timezone(timezone), "manual")
    if geography_changed and existing_source == "auto":
        return TimezoneWrite(_auto_timezone(state=state, country_code=country_code), "auto")
    return TimezoneWrite(None, None)
