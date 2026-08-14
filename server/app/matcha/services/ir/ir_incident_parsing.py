"""Pure IR-incident parsing/generation helpers — no DB, no routes.

Moved from routes/ir_incidents/_shared.py (refactor round 2, stage 3 follow-up).
Split out from the route package so `create_incident_core` (this package's sole
real caller besides the route re-export) doesn't have to lazily import the whole
IR router `__init__.py` just to reach three pure functions.
"""
import re
import secrets
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from .._shared.time import utc_now_naive as _utc_now_naive

# Severe keywords that mandate an immediate OSHA reportable-event call
# (8 hours for fatality, 24 hours for amputation / lost eye / in-patient
# hospitalization — 29 CFR 1904.39). Detection runs on incident creation
# against the title+description; a hit flips severity to critical and
# pushes the emergency alert card into the Copilot transcript.
_OSHA_REPORTABLE_KEYWORD_RE = re.compile(
    r"\b("
    r"fatalit(?:y|ies)"
    r"|passed\s+away"
    r"|(?:was|were)\s+killed"
    r"|(?:was|were|has)\s+died"
    r"|amputat(?:e|ed|ion|ing)"
    r"|lost\s+(?:an?\s+|his\s+|her\s+|their\s+)?eye"
    r"|hospitali[sz]ed"
    r"|hospitali[sz]ation"
    r"|in-?patient\s+admission"
    r")\b",
    re.IGNORECASE,
)


def _detect_osha_reportable_keywords(text: Optional[str]) -> bool:
    """True if text mentions a 29 CFR 1904.39 reportable-event term.

    False on None / empty / no match. Boundary-anchored so false-friends
    like "studied" or "skilled" don't match (no overlap with the pattern
    anyway, but the word boundary keeps it safe against future additions).
    """
    if not text:
        return False
    return bool(_OSHA_REPORTABLE_KEYWORD_RE.search(text))


def generate_incident_number() -> str:
    """Generate a unique incident number."""
    now = datetime.now(timezone.utc)
    random_suffix = secrets.token_hex(2).upper()
    return f"IR-{now.year}-{now.month:02d}-{random_suffix}"


# Ordered so more-specific multi-word terms (e.g. "day before yesterday") match
# before shorter ones that would otherwise shadow them (e.g. "yesterday") —
# "day before yesterday" isn't shadowed by the "yesterday" pattern matching
# first. Each entry is (pattern, day_offset_from_today, default_hour) — the
# default_hour is used when the remainder has no clock time of its own;
# "last night" gets an evening default (21:00) since it implies a specific
# part of the day, unlike a bare "yesterday".
_RELATIVE_DAY_TERMS: tuple[tuple[re.Pattern, int, int], ...] = (
    (re.compile(r"\bday before yesterday\b", re.IGNORECASE), -2, 12),
    (re.compile(r"\byesterday\b", re.IGNORECASE), -1, 12),
    (re.compile(r"\blast night\b", re.IGNORECASE), -1, 21),
    (re.compile(r"\b(?:today|tonight|this morning|this afternoon|this evening)\b", re.IGNORECASE), 0, 12),
)
_DAYS_AGO_RE = re.compile(r"\b(\d+)\s+days?\s+ago\b", re.IGNORECASE)
_EXPLICIT_YEAR_RE = re.compile(r"\b\d{4}\b")


def _relative_day_match(text: str) -> Optional[tuple[int, int, str]]:
    """Find a relative-day term in ``text``. Returns (day_offset, default_hour,
    remainder) for the first match, or None. ``remainder`` is ``text`` with the
    matched term blanked out, whitespace collapsed — fed to dateutil so a
    spoken clock time ("...around 3pm") still lands on the right day."""
    m = _DAYS_AGO_RE.search(text)
    if m:
        offset = -int(m.group(1))
        remainder = re.sub(r"\s+", " ", _DAYS_AGO_RE.sub(" ", text, count=1)).strip()
        return offset, 12, remainder
    for pattern, offset, default_hour in _RELATIVE_DAY_TERMS:
        if pattern.search(text):
            remainder = re.sub(r"\s+", " ", pattern.sub(" ", text, count=1)).strip()
            return offset, default_hour, remainder
    return None


def _clamp_future_occurred_at(parsed: datetime, original_text: str) -> datetime:
    """Guard against dateutil defaulting a yearless date into the future.

    "Dec 30" parsed in mid-2026 with no default year defaults to the current
    year, landing months ahead — an incident can't have occurred in the
    future. If the parse lands more than 26h ahead of now AND the original
    text had no explicit 4-digit year, retry a year earlier; if it's still in
    the future (or the retry itself fails), fall back to NOW() rather than
    ever returning/raising on a bad future date.
    """
    now = _utc_now_naive()
    if parsed <= now + timedelta(hours=26):
        return parsed
    if _EXPLICIT_YEAR_RE.search(original_text):
        return now
    try:
        retried = parsed.replace(year=parsed.year - 1)
    except ValueError:  # e.g. Feb 29 in a non-leap year
        retried = parsed - timedelta(days=365)
    return retried if retried <= now + timedelta(hours=26) else now


def _parse_occurred_at(value) -> datetime:
    """Coerce IR submit `occurred_at` to a naive UTC datetime.

    Accepts a real datetime (from rich clients / admin tooling) or a free
    text string from the slim submit form ("yesterday at 3pm", "May 1 4pm").
    Falls back to NOW() on parse failure rather than 400'ing — incident
    capture should never block on a date typo.
    """
    if isinstance(value, datetime):
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        # Typed API dates are unambiguous, so never retain a future occurrence.
        return min(value, _utc_now_naive())
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return _utc_now_naive()
        try:
            from dateutil import parser as _date_parser
            relative = _relative_day_match(text)
            if relative is not None:
                offset, default_hour, remainder = relative
                base_date = (datetime.now(timezone.utc) + timedelta(days=offset)).date()
                default_dt = datetime.combine(base_date, time(default_hour, 0))
                if remainder:
                    try:
                        parsed = _date_parser.parse(remainder, fuzzy=True, default=default_dt)
                    except (ValueError, OverflowError, TypeError):
                        parsed = default_dt
                else:
                    parsed = default_dt
            else:
                parsed = _date_parser.parse(text, fuzzy=True)
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return _clamp_future_occurred_at(parsed, text)
        except (ValueError, OverflowError, TypeError):
            return _utc_now_naive()
    return _utc_now_naive()
