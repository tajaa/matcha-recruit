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


# Title abbreviations, spelled out so "VP of Ops" and "Vice President,
# Operations" are the same title.
_TITLE_ABBREVIATIONS = {
    "vp": "vice president", "svp": "senior vice president", "evp": "executive vice president",
    "avp": "assistant vice president", "coo": "chief operating officer", "ceo": "chief executive officer",
    "cfo": "chief financial officer", "cto": "chief technology officer", "cmo": "chief marketing officer",
    "cro": "chief revenue officer", "cpo": "chief product officer", "ops": "operations", "sr": "senior",
    "jr": "junior", "mgr": "manager", "dir": "director", "gm": "general manager",
    "hr": "human resources", "chro": "chief human resources officer",
}
# Words a board adds around a title without changing the job.
_TITLE_FILLER = {"of", "and", "the", "for", "a", "an", "to", "at", "in", "remote", "hybrid", "onsite", "on",
                 "site", "full", "part", "time", "us", "usa"}
# Employer names that hide the employer.
_UNNAMED_EMPLOYERS = {"confidential", "undisclosed", "stealth", "anonymous"}


def title_words(title: str) -> set[str]:
    words: list[str] = []
    for word in _words(title):
        words += _TITLE_ABBREVIATIONS.get(word, word).split()
    return {w for w in words if w not in _TITLE_FILLER}


def same_title(a: str, b: str) -> bool:
    """Whether two titles name the same job. Abbreviations are spelled out and
    one side may add a little (a city, a team): "COO - Austin" is "Chief
    Operating Officer", but "Operations Associate / Head of Operations" is not
    "Founding COO / Head of Operations"."""
    x, y = title_words(a), title_words(b)
    if not x or not y:
        return False
    both = len(x & y)
    return x == y or (both / len(x) >= 0.75 and both / len(y) >= 0.6)


# Words that say how senior a title is, not what the job is.
_SENIORITY = {"chief", "head", "vice", "president", "senior", "executive", "director", "officer", "lead",
              "global", "principal", "staff", "manager", "assistant", "associate", "junior", "general",
              "group", "deputy", "interim", "acting", "founding", "first", "sr", "team", "leader"}


def _stems(words: set[str]) -> set[str]:
    return {w[:5] for w in words}


def related_title(title: str, wanted: list[str]) -> bool:
    """Whether a posting's title is about the work one of the wanted titles
    is ("Director of Operations" for "Chief Operating Officer", "HR Business
    Partner" for "Head of HR"), so a board posting that only names a wanted
    title somewhere ("Software Engineer") isn't read as a lead. Level is the
    screen's to judge; True when nothing is wanted."""
    if not any(w for w in wanted):
        return True
    words = _stems(title_words(title))
    for want in wanted:
        core = title_words(want) - _SENIORITY or title_words(want)
        if _stems(core) & words:
            return True
    return False


def named_employer(company: str) -> str:
    """The employer's name run together for comparing ("BMW Group" -> bmw), or
    "" when the listing hides it ("Confidential")."""
    words = [w for w in company_key(company).split() if w not in _UNNAMED_EMPLOYERS]
    return "".join(w for w in words if w not in _GENERIC_NAME_WORDS) or "".join(words)


def same_employer(company: str, other: str) -> bool | None:
    """Whether `other` (an ATS board's name for itself, "hellobackpack", or a
    page's hiring organization) is `company`'s employer: it contains one of
    the name's distinctive words, or the whole short name. None when either
    side names nobody, so there is nothing to compare."""
    there = "".join(_words(other))
    if not there or not named_employer(company):
        return None
    words = name_words(company) - _UNNAMED_EMPLOYERS
    if words:
        return any(w in there for w in words)
    return named_employer(company) in there


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


_REMOTE = re.compile(r"\b(remote|work from home|anywhere)\b", re.I)
_NOT_REMOTE = re.compile(r"\b(?:non|not)[- ]?remote\b", re.I)
_HYBRID = re.compile(r"\bhybrid\b", re.I)
# The word set off from the role as a tag: "Designer (Remote)", "Remote -
# Designer", "Designer | US Remote", "Designer (Remote or Hybrid)". Inside the
# role it is not one: "Remote Sensing Analyst", "Hybrid Cloud Engineer",
# "Nurse - Remote Patient Monitoring".
_EDGE = r"(?:[\(\)\[\]\-–—|,:/]|\bor\b)"


def _tag(words: str) -> re.Pattern:
    return re.compile(rf"(?:^|{_EDGE})\s*(?:(?:us|usa)\s+)?(?:{words})(?:\s+(?:us|usa|only|first|eligible|ok))?"
                      rf"\s*(?:$|{_EDGE})", re.I)


_REMOTE_TAG = _tag("remote|work from home|wfh")
_HYBRID_TAG = _tag("hybrid")


def is_remote(*texts: str | None, flag: bool | None = None, title: str | None = None) -> bool | None:
    """Whether a posting is remote, from its location `texts`, its `title` and
    the source's own `flag` (Google's work_from_home), the posting's own words
    first: True when a text says remote ("Remote - US", "Anywhere") or the
    title carries it as a tag; False when they say hybrid instead (a hybrid
    job has an office to go to, whatever a source inferred); else `flag`."""
    said = [_NOT_REMOTE.sub(" ", text) for text in texts if text]
    title = _NOT_REMOTE.sub(" ", title or "")
    if any(_REMOTE.search(text) for text in said) or _REMOTE_TAG.search(title):
        return True
    if any(_HYBRID.search(text) for text in said) or _HYBRID_TAG.search(title):
        return False
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
