"""Small pure helpers for posting data: dedupe keys, states, remote, links."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

_COMPANY_SUFFIXES = {
    "inc", "llc", "ltd", "corp", "corporation", "co", "company", "the", "plc",
    "lp", "llp", "gmbh", "incorporated", "limited",
}
_NON_WORD = re.compile(r"[^a-z0-9]+")

STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}
_CODES = set(STATES.values())


def _words(value: str) -> list[str]:
    return [w for w in _NON_WORD.split((value or "").lower()) if w]


def company_key(company: str) -> str:
    words = [w for w in _words(company) if w not in _COMPANY_SUFFIXES]
    return " ".join(words)


def dedupe_key(company: str, title: str, location: str) -> str:
    """Same company, same title, same city: the same job seen twice.

    Google Jobs lists one posting once per board it appears on; the ATS copy
    and an aggregator copy collapse here.
    """
    city = (location or "").split(",")[0]
    return "|".join((company_key(company), " ".join(_words(title)), " ".join(_words(city))))[:400]


# Words too common in employer names to say two names are the same employer.
_GENERIC_NAME_WORDS = {
    "health", "healthcare", "group", "global", "services", "service", "partners", "capital",
    "systems", "solutions", "international", "holdings", "hospital", "hospitals", "clinic",
    "america", "american", "national", "united", "medical", "management", "consulting",
    "technologies", "technology", "corporate", "enterprises", "industries", "network",
    "foundation", "university", "center", "centre", "staffing", "search", "executive",
    "recruiting", "consultants", "associates", "office", "offices", "company", "family",
}


def name_words(company: str) -> set[str]:
    """The distinctive words of an employer name ("Beth Israel Lahey Health" ->
    beth, israel, lahey)."""
    return {w for w in company_key(company).split() if len(w) >= 4 and w not in _GENERIC_NAME_WORDS}


def same_posting(a_title: str, a_company: str, b_title: str, b_company: str) -> bool:
    """The same job listed under two employer names: the same title, and the
    names share a distinctive word ("Beth Israel Lahey Health" and "Lahey
    Clinic Hospital, Inc." posting the same SVP & COO requisition)."""
    if " ".join(_words(a_title)) != " ".join(_words(b_title)):
        return False
    return bool(name_words(a_company) & name_words(b_company))


def state_of(location: str) -> str | None:
    """A two-letter US state code from "Austin, TX", "Austin, Texas" or "Texas"."""
    if not location:
        return None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    for part in reversed(parts):
        bare = re.sub(r"\s*\(.*\)\s*$", "", part).strip()
        upper = bare.upper()
        if upper in _CODES and len(bare) == 2:
            return upper
        # "TX 78701"
        head = upper.split(" ")[0]
        if head in _CODES and re.fullmatch(r"[A-Z]{2}\s+\d{5}(-\d{4})?", upper):
            return head
        code = STATES.get(bare.lower())
        if code:
            return code
    return None


def is_remote(*texts: str | None, flag: bool | None = None) -> bool | None:
    if flag is True:
        return True
    for text in texts:
        if text and re.search(r"\b(remote|work from home|anywhere)\b", text, re.I):
            return True
    return flag


def http_url(value) -> str | None:
    """`value` if it is a plain http(s) URL with a host and no credentials."""
    if not isinstance(value, str):
        return None
    url = value.strip()
    if len(url) > 2048:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    return url


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def clean_text(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


_AGE = re.compile(r"(\d+)\+?\s*(minute|hour|day|week|month|year)s?\s+ago", re.I)
_AGE_HOURS = {"minute": 1 / 60, "hour": 1, "day": 24, "week": 168, "month": 720, "year": 8760}


def posted_age_hours(text: str | None) -> float | None:
    """Hours since posting from Google's "3 days ago" / "30+ days ago"."""
    if not text:
        return None
    if re.search(r"\b(just posted|today)\b", text, re.I):
        return 0.0
    match = _AGE.search(text)
    if not match:
        return None
    return float(match.group(1)) * _AGE_HOURS[match.group(2).lower()]
