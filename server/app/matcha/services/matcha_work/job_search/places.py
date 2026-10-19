"""Whether a job is in a place the person named.

A search with places in it (`criteria.locations`, other than "Remote" and the
nationwide words) keeps a job only when one of the places its posting names
is within `NEAR_MILES` of one of theirs, or when it is remote and they'd take
remote (`fits`). Code decides from the posting's own location text, never a
model: the text is split into the places it names ("El Segundo, CA and/or
Burbank" is two), and each is put on the map with the US Census Bureau's
gazetteer of places and counties (`data/us_places.tsv.gz`, built by
`server/scripts/build_job_places.py`). A job none of whose places can be put
on the map is not kept, and neither is a remote job open only outside the
country of every place they named.

A name without a state ("Burbank") is the namesake nearest the person's
places (Burbank, CA for a Los Angeles search), else the largest. A named
state ("Texas") takes any job in it; a place outside the US ("London") is
matched by name, since the gazetteer is the US only. Distance is miles in a
straight line between the gazetteer's points (a county's is near its middle).
"""
from __future__ import annotations

import gzip
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import normalize

DATA = Path(__file__).with_name("data") / "us_places.tsv.gz"
NEAR_MILES = 50.0
EARTH_MILES = 3958.8

# The words a search names no place with (phases.NATIONWIDE plus remote).
ANYWHERE = {"united states", "us", "usa", "u s", "u s a", "america", "nationwide", "anywhere", "national",
            "across the country", "across the us", "the us", "remote", "remote us", "us remote", "remote usa",
            "us only", "united states only", "us based", "anywhere in the us", "anywhere in the united states",
            "anywhere in america", "anywhere us", "anywhere in us", "within the us", "all us", "all 50 states",
            "continental us", "contiguous us", "lower 48", "countrywide", "nationally", "open to relocation",
            "willing to relocate"}
# Words around a place that don't change it: "Hybrid (San Diego, CA)", "NYC HQ".
_NOISE = re.compile(
    r"\b(hybrid|remote|on[- ]?site|in[- ]office|office|offices|hq|headquarters|flexible|work from home|wfh|"
    r"greater|metropolitan area|metro area|metro|area|region|downtown|based|or nearby|nearby|preferred|"
    r"location|locations|multiple|various|any)\b",
)
_SPLIT = re.compile(r"\s*(?:;|\||/|•|·|\n|\(|\)|\band/or\b|\bor\b| & | - | – | — )\s*")
# Oregon's code, before the text is lowercased: "Salem, OR" is not "salem or".
_OREGON = re.compile(r"\bOR\b")
_REMOTE = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\banywhere\b|\bdistributed\b")
_NOT_REMOTE = re.compile(r"\b(?:not|no|non)[- ]remote\b")
# Names the gazetteer doesn't carry, as the place to measure from.
ALIASES = {
    "nyc": ("new york", "NY"), "new york city": ("new york", "NY"), "manhattan": ("new york", "NY"),
    "brooklyn": ("new york", "NY"), "queens": ("new york", "NY"), "bronx": ("new york", "NY"),
    "the bronx": ("new york", "NY"), "staten island": ("new york", "NY"),
    "sf": ("san francisco", "CA"), "bay area": ("san francisco", "CA"), "sf bay": ("san francisco", "CA"),
    "sf bay area": ("san francisco", "CA"), "san francisco bay": ("san francisco", "CA"),
    "san francisco bay area": ("san francisco", "CA"), "silicon valley": ("san jose", "CA"),
    "la": ("los angeles", "CA"), "hollywood": ("los angeles", "CA"), "north hollywood": ("los angeles", "CA"),
    "playa vista": ("los angeles", "CA"), "venice beach": ("los angeles", "CA"),
    "dc": ("washington", "DC"), "washington dc": ("washington", "DC"), "washington d c": ("washington", "DC"),
    "district of columbia": ("washington", "DC"), "dmv": ("washington", "DC"),
    "philly": ("philadelphia", "PA"), "nola": ("new orleans", "LA"), "vegas": ("las vegas", "NV"),
    "dfw": ("dallas", "TX"), "twin cities": ("minneapolis", "MN"), "research triangle": ("raleigh", "NC"),
    # Regions, measured from their biggest city.
    "southern california": ("los angeles", "CA"), "socal": ("los angeles", "CA"),
    "northern california": ("san francisco", "CA"), "norcal": ("san francisco", "CA"),
    "new england": ("boston", "MA"), "pacific northwest": ("seattle", "WA"), "pnw": ("seattle", "WA"),
    "tri state": ("new york", "NY"), "tristate": ("new york", "NY"), "tri state area": ("new york", "NY"),
    "south florida": ("miami", "FL"), "oc": ("orange county", "CA"), "dc area": ("washington", "DC"),
    "midwest": ("chicago", "IL"), "the midwest": ("chicago", "IL"), "east coast": ("new york", "NY"),
    "the east coast": ("new york", "NY"), "west coast": ("los angeles", "CA"), "the west coast": ("los angeles", "CA"),
    "northeast": ("new york", "NY"), "southeast": ("atlanta", "GA"), "southwest": ("phoenix", "AZ"),
    "mountain west": ("denver", "CO"),
}
# Cities abroad that share a name with a small US town: named alone ("London",
# "Paris"), they are the city abroad.
WORLD_CITIES = {
    "london": "united kingdom", "paris": "france", "berlin": "germany", "dublin": "ireland", "toronto": "canada",
    "vancouver": "canada", "montreal": "canada", "madrid": "spain", "barcelona": "spain", "lisbon": "portugal",
    "amsterdam": "netherlands", "rome": "italy", "milan": "italy", "munich": "germany", "zurich": "switzerland",
    "geneva": "switzerland", "stockholm": "sweden", "copenhagen": "denmark", "oslo": "norway",
    "helsinki": "finland", "warsaw": "poland", "prague": "czech republic", "vienna": "austria",
    "budapest": "hungary", "athens": "greece", "istanbul": "turkey", "tel aviv": "israel",
    "dubai": "united arab emirates", "singapore": "singapore", "tokyo": "japan", "seoul": "south korea",
    "sydney": "australia", "melbourne": "australia", "bangalore": "india", "bengaluru": "india", "mumbai": "india",
    "delhi": "india", "new delhi": "india", "hyderabad": "india", "mexico city": "mexico", "sao paulo": "brazil",
    "buenos aires": "argentina", "manila": "philippines", "jakarta": "indonesia", "edinburgh": "united kingdom",
    "manchester": "united kingdom", "brussels": "belgium", "frankfurt": "germany", "hamburg": "germany",
    "cambridge uk": "united kingdom", "oxford uk": "united kingdom",
}
# A state's name alone is the state, though a town shares it ("California,
# PA"); New York and Washington alone are the cities.
_CITY_FIRST = {"new york", "washington"}
# Places outside the US a posting names, by how it names them. Matched as
# words, so a US place spelled the same ("Paris, TX") is still the state's.
COUNTRIES = {
    "canada", "uk", "united kingdom", "england", "scotland", "wales", "ireland", "germany", "france", "spain",
    "portugal", "italy", "netherlands", "belgium", "switzerland", "austria", "sweden", "norway", "denmark",
    "finland", "poland", "czech republic", "czechia", "romania", "hungary", "greece", "israel", "india",
    "singapore", "australia", "new zealand", "japan", "china", "hong kong", "taiwan", "korea", "south korea",
    "philippines", "vietnam", "thailand", "indonesia", "malaysia", "mexico", "brazil", "argentina", "chile",
    "colombia", "peru", "costa rica", "south africa", "nigeria", "kenya", "egypt", "uae", "united arab emirates",
    "saudi arabia", "qatar", "turkey", "ukraine", "estonia", "latvia", "lithuania", "europe", "emea", "apac",
    "latam", "eu", "asia",
}
_PROVINCES = {"ontario", "quebec", "british columbia", "alberta", "manitoba", "saskatchewan", "nova scotia",
              "new brunswick", "on", "bc", "ab", "qc"}
# One name per country, whatever a posting or a person calls it.
_COUNTRY_KEY = {"uk": "united kingdom", "england": "united kingdom", "scotland": "united kingdom",
                "wales": "united kingdom", "czechia": "czech republic", "korea": "south korea",
                "uae": "united arab emirates", "eu": "europe"}


def _country(part: str) -> str | None:
    """The country a location part names, under one name; None for anything else."""
    if part in _PROVINCES:
        return "canada"
    if part in COUNTRIES:
        return _COUNTRY_KEY.get(part, part)
    return None
_US = {"united states", "united states of america", "usa", "us", "u s", "u s a", "america"}

Point = tuple[float, float]


@dataclass(frozen=True)
class Entry:
    """One gazetteer place: a city, town or CDP, or a county."""
    state: str
    lat: float
    lon: float
    sqmi: float
    county: bool

    @property
    def point(self) -> Point:
        return (self.lat, self.lon)


@dataclass(frozen=True)
class Target:
    """A place the person named: on the map (`points`), a whole US state
    (`state`), or, off the gazetteer (outside the US, or a name it doesn't
    carry), matched by its name (`name`). `abroad` when they said a country
    other than the US, and `country` which (a country alone keeps every job
    its postings place there)."""
    label: str
    points: tuple[Point, ...] = ()
    state: str | None = None
    name: str | None = None
    abroad: bool = False
    country: str | None = None


@dataclass(frozen=True)
class Verdict:
    keep: bool
    why: str


def place_key(name: str) -> str:
    """A place's name for looking it up: lower case, no punctuation, "Saint"
    and "St." both "st", "Ft." "fort", "Mt." "mount"."""
    text = str(name or "").lower().replace("&", " and ").replace("’", "'")
    text = re.sub(r"[.'`]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    text = re.sub(r"^saint\b", "st", text)
    text = re.sub(r"^ft\b", "fort", text)
    text = re.sub(r"^mt\b", "mount", text)
    return " ".join(text.split())


@lru_cache(maxsize=1)
def _index() -> dict[str, tuple[Entry, ...]]:
    """The gazetteer by `place_key`: each name's places across the states."""
    found: dict[str, list[Entry]] = {}
    with gzip.open(DATA, "rt", encoding="utf-8") as rows:
        for line in rows:
            kind, key, state, lat, lon, sqmi = line.rstrip("\n").split("\t")
            found.setdefault(key, []).append(Entry(state, float(lat), float(lon), float(sqmi), kind == "county"))
    return {key: tuple(entries) for key, entries in found.items()}


def miles(a: Point, b: Point) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_MILES * math.asin(min(1.0, math.sqrt(h)))


def _state(text: str) -> str | None:
    """A US state code from "CA", "California" or "Calif"; None otherwise."""
    key = place_key(text)
    code = key.upper()
    if code in normalize.STATES.values():
        return code
    return normalize.STATES.get(key) or normalize.STATES.get(key.rstrip("."))


@dataclass(frozen=True)
class Named:
    """One place a location text names: its place name, the state it gives,
    and whether it is outside the US (and in which country, when it says)."""
    name: str
    state: str | None = None
    abroad: bool = False
    country: str | None = None


_ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b")
# Workday's and others' "US-CA-Irvine".
_CODED = re.compile(r"^\s*(?:us|usa)\s*-\s*([a-z]{2})\s*-\s*(.+)$")


def _part(text: str) -> str:
    """One comma part as a place name: an alias as written ("Bay Area"), else
    without the words around it ("Greater Boston Area" -> boston)."""
    key = place_key(text)
    if key in ALIASES:
        return key
    return place_key(_NOISE.sub(" ", text))


def named(text: str) -> list[Named]:
    """The places a posting's or a person's location text names, in order.
    "Hybrid (San Diego, CA)" -> San Diego, CA; "Remote - United States" ->
    nothing; "London, United Kingdom" -> London, abroad; "Texas" -> the state."""
    out: list[Named] = []
    for fragment in _SPLIT.split(_ZIP.sub(" ", _OREGON.sub("Oregon", str(text or "")).lower())):
        coded = _CODED.match(fragment)
        if coded:
            fragment = f"{coded.group(2)}, {coded.group(1)}"
        parts = [p for p in (_part(part) for part in fragment.split(",")) if p]
        if not parts:
            continue
        state = None
        abroad = False
        country = None
        rest = []
        # "Peru, IN" is Indiana's: a country's name before a state is a town.
        stated = any(_state(part) for part in parts[1:])
        for i, part in enumerate(parts):
            if part in _US:
                continue
            named_country = _country(part)
            if named_country and not (i == 0 and stated):
                abroad = True
                country = country or named_country
                continue
            code = _state(part) if rest else None
            if code and not state:
                state = code
                continue
            rest.append(part)
        if not rest:
            if state:
                out.append(Named("", state))
            elif abroad:
                out.append(Named("", None, abroad=True, country=country))
            continue
        name = rest[0]
        if name in ANYWHERE:
            continue
        if not state and len(rest) == 1 and " " in name and name not in ALIASES and not _state(name):
            # "Austin TX", "Denver Colorado": a city and its state with no comma.
            head, _sep, tail = name.rpartition(" ")
            code = _state(tail)
            if code and head and head not in ANYWHERE and not _state(head):
                name, state = head, code
        lone = _state(name) if not state and len(rest) == 1 and name not in ALIASES else None
        if lone and (len(name) == 2 or name not in _CITY_FIRST):
            out.append(Named("", lone))  # "California", "TX"
            continue
        if not state and not abroad and name in WORLD_CITIES:
            abroad, country = True, WORLD_CITIES[name]
        out.append(Named(name, state, abroad, country=country if abroad else None))
    return out


def _names_us(text: str) -> bool:
    """Whether a location text says the US by name ("Remote - United States")."""
    return any(place_key(part) in _US
               for fragment in _SPLIT.split(str(text or "").lower()) for part in fragment.split(","))


def _entries(place: Named) -> tuple[Entry, ...]:
    name, state = place.name, place.state
    if name in ALIASES:
        name, state = ALIASES[name][0], state or ALIASES[name][1]
    index = _index()
    found = index.get(name, ())
    if not found and not name.endswith(" county") and name.endswith(" co"):
        found = index.get(name[:-3] + " county", ())
    if state:
        found = tuple(e for e in found if e.state == state)
    return found


def _nearest(entries: tuple[Entry, ...], anchors: tuple[Point, ...]) -> Entry | None:
    if not entries:
        return None
    if anchors:
        return min(entries, key=lambda e: min(miles(e.point, a) for a in anchors))
    return max(entries, key=lambda e: (not e.county, e.sqmi))


@lru_cache(maxsize=512)
def target(text: str) -> Target | None:
    """A place the person named, ready to measure from; None for "Remote",
    nationwide words and text that names no place."""
    places = named(text)
    if not places:
        return None
    place = places[0]
    if not place.name:
        if place.state:
            return Target(label=text, state=place.state)
        if place.abroad:
            # A country alone ("Canada"): every job its postings place there.
            return Target(label=text, abroad=True, country=place.country)
        return None
    if place.abroad:
        return Target(label=text, name=place.name, abroad=True, country=place.country)
    entry = _nearest(_entries(place), ())
    if entry is None:
        # Not a place the gazetteer carries ("London", "Toronto"): by name.
        return Target(label=text, name=place.name)
    return Target(label=text, points=(entry.point,), name=place.name)


def target_near(text: str, around: str | None) -> Target | None:
    """A place named inside another one: "Pasadena" around "Los Angeles, CA"
    is California's, not the largest Pasadena anywhere. Only a same-named
    place in `around`'s state and within `NEAR_MILES` of its city counts;
    None when the gazetteer has none there (a neighborhood, a landmark).
    Text that names its own state, or no `around`, is `target(text)`."""
    places = named(text)
    context = target(around) if around else None
    place = places[0] if places else None
    if place is None or not place.name or place.abroad or place.state or context is None:
        return target(text)
    if context.abroad or not (context.points or context.state):
        return None
    entries = _entries(place)
    state = context.state or next((n.state for n in named(around) if n.state), None)
    if state:
        entries = tuple(e for e in entries if e.state == state)
    if context.points:
        entries = tuple(e for e in entries if min(miles(e.point, a) for a in context.points) <= NEAR_MILES)
    entry = _nearest(entries, context.points)
    return Target(label=text, points=(entry.point,), name=place.name) if entry else None


def targets(criteria: dict) -> list[Target]:
    """The places a search keeps jobs in; empty when it named none."""
    out = []
    for text in criteria.get("locations") or []:
        if isinstance(text, str) and place_key(text) not in ANYWHERE:
            found = target(text)
            if found is not None:
                out.append(found)
    return out


def takes_remote(criteria: dict) -> bool:
    return criteria.get("remote") != "onsite_only"


def is_remote(location: str, remote: bool | None) -> bool:
    text = str(location or "").lower()
    return remote is True or (bool(_REMOTE.search(text)) and not _NOT_REMOTE.search(text))


def _countries_wanted(wanted: list[Target]) -> set[str]:
    """The countries the person's places are in: each abroad place's, and
    "us" for any place on the map, any state, or any US name off the map."""
    out = {t.country for t in wanted if t.country}
    if any(not t.abroad for t in wanted):
        out.add("us")
    return out


def judge(location: str, remote: bool | None, criteria: dict) -> Verdict:
    """Whether a job at `location` (`remote` as its posting says) is kept by
    a search with these criteria, and why."""
    wanted = targets(criteria)
    if not wanted:
        return Verdict(True, "no places named")
    places = named(location)
    countries = _countries_wanted(wanted)
    us_only = countries == {"us"}
    if is_remote(location, remote) and takes_remote(criteria):
        # A remote job open only in countries none of their places are in.
        if places and all(p.abroad and p.country for p in places) \
                and {p.country for p in places}.isdisjoint(countries):
            return Verdict(False, "remote outside the US" if us_only else "remote outside " + ", ".join(sorted(countries)))
        if not places and "us" not in countries and _names_us(location):
            return Verdict(False, "remote in the US only")
        return Verdict(True, "remote")
    anchors = tuple(p for t in wanted for p in t.points)
    best: tuple[float, str] | None = None
    for place in places:
        for t in wanted:
            if t.state and not t.points and (place.state == t.state or _state_of(place, anchors) == t.state):
                return Verdict(True, f"in {t.label}")
            if t.name and not t.points and place.name and _same_name(place.name, t.name):
                return Verdict(True, f"in {t.label}")
            if t.country and not t.name and place.abroad and place.country == t.country:
                return Verdict(True, f"in {t.label}")
        if place.abroad or not place.name:
            continue
        entry = _nearest(_entries(place), anchors)
        if entry is None:
            continue
        for t in wanted:
            for point in t.points:
                distance = miles(entry.point, point)
                if best is None or distance < best[0]:
                    best = (distance, t.label)
    if best is not None and best[0] <= NEAR_MILES:
        return Verdict(True, f"{best[0]:.0f} mi from {best[1]}")
    if best is not None:
        return Verdict(False, f"{best[0]:.0f} mi from {best[1]}")
    if places and all(p.abroad for p in places):
        return Verdict(False, "outside the US" if us_only else "not in " + ", ".join(t.label for t in wanted))
    if places and all(not t.points for t in wanted):
        return Verdict(False, "not in " + ", ".join(t.label for t in wanted))
    return Verdict(False, "location not placed" if places else "no location")


def _same_name(place: str, wanted: str) -> bool:
    """A place off the gazetteer, by name: "london" is "greater london"."""
    return place == wanted or f" {wanted} " in f" {place} "


def _state_of(place: Named, anchors: tuple[Point, ...]) -> str | None:
    if place.state or not place.name:
        return place.state
    entry = _nearest(_entries(place), anchors)
    return entry.state if entry is not None else None


def fits(location: str, remote: bool | None, criteria: dict) -> bool:
    return judge(location, remote, criteria).keep
