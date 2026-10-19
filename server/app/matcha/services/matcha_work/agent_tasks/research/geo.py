"""How far a finding is from a place the person named, and which way.

A brief's `near` ("2100 Barton Springs Rd", "Santa Monica") is put on the
map once per task, its `anchor`, kept in the plan: a street address through
the US Census geocoder, else a city or town by name from the offline Census
gazetteer job search uses (`job_search/places.py`). A landmark neither knows
("Lady Bird Lake") isn't found, and distances from it are unknown. A
finding's own point comes from its page's schema.org `geo` or its address
through the Census geocoder. (Google Maps was a source until 2026-10-18:
Espresso uses no Google API now.)

Distance (miles in a straight line) and direction (the quarter of the compass
it lies in from the anchor: north is within 45 degrees of due north) are then
arithmetic, never a model's claim (`fields.COMPUTED`). Each is as good as the
point it came from: verified from page data or a verified address; claimed
from an address only claimed on another page.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Awaitable, Callable

import httpx

from . import fields as F

logger = logging.getLogger(__name__)

EARTH_MILES = 3958.8
CENSUS_SECONDS = 15.0

Point = tuple[float, float]
Geocode = Callable[[str], Awaitable[Point | None]]


def point_of(raw: Any) -> Point | None:
    """(lat, lng) from `{latitude, longitude}` or `{lat, lng}`, or None."""
    if not isinstance(raw, dict):
        return None
    lat = raw.get("latitude", raw.get("lat"))
    lng = raw.get("longitude", raw.get("lng"))
    try:
        point = (float(lat), float(lng))
    except (TypeError, ValueError):
        return None
    if not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180) or point == (0.0, 0.0):
        return None
    return point


def miles(a: Point, b: Point) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_MILES * math.asin(min(1.0, math.sqrt(h)))


def bearing(a: Point, b: Point) -> float:
    """Degrees clockwise from north, from `a` to `b`."""
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    x = math.sin(lng2 - lng1) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lng2 - lng1)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def quarter(degrees: float) -> str:
    return ("north", "east", "south", "west")[int(((degrees + 45) % 360) // 90)]


def distance_fields(point: Point, anchor: dict, *, status: str, origin: str, url: str | None,
                    how: str) -> dict:
    """The `distance` and `direction` entries of a finding at `point`."""
    home = (float(anchor["lat"]), float(anchor["lng"]))
    away = round(miles(home, point), 1)
    way = quarter(bearing(home, point))
    evidence = {"quote": F.clean_text(f"{away:g} mi {way} of {anchor['name']} ({how})", 300),
                "url": url, "origin": origin, "point": [round(point[0], 6), round(point[1], 6)]}
    return {
        "distance": {"value": away, "status": status, "display": f"{away:,.1f} mi {way}", "evidence": evidence},
        "direction": {"value": [way], "status": status, "display": F.DIRECTIONS[way], "evidence": evidence},
    }


def page_point(page: dict, title: str) -> Point | None:
    """The page's one listing or place's schema.org `geo`, if it gives one."""
    for key in ("listings", "places"):
        node = F.the_one(page.get(key) or [], title)
        if node and point_of(node.get("geo")):
            return point_of(node.get("geo"))
    return None


async def census_point(line: str) -> Point | None:
    """A street address on the map through the US Census geocoder (US only):
    None when it has no such address, `GeocoderUnavailable` when it didn't
    answer (so an anchor lookup is tried again rather than kept as not found)."""
    from app.core.services import geo as core_geo

    async with httpx.AsyncClient(timeout=CENSUS_SECONDS) as client:
        found = await core_geo.geocode_or_raise(client, " ".join(str(line or "").split()))
    return (found["lat"], found["lng"]) if found else None


def anchor_query(near: str, location: str | None) -> str:
    """The place as searched: with the task's city unless it already says it."""
    from .contracts import names_place

    return near if not location or names_place(near, location) else f"{near}, {location}"


def town_point(near: str, location: str | None = None) -> tuple[str, Point] | None:
    """A city or town named on its own ("Santa Monica", "Austin, TX") from
    the offline Census gazetteer: `(its name, its point)`. Anything that only
    mentions one ("Lady Bird Lake, Austin") is not it. A name with no state of
    its own is the one in the task's `location` ("Pasadena" in a Los Angeles
    search is California's, never Texas's: `places.target_near`), and none
    when that area has no place by that name."""
    from app.matcha.services.matcha_work.job_search import places

    found = places.target_near(near, location)
    if found is None or not found.points or not found.name:
        return None
    head = places.place_key(near.split(",")[0])
    return (found.name.title(), found.points[0]) if head == found.name else None


async def resolve_anchor(near: str, location: str | None, *, geocode: Geocode) -> dict:
    """`{name, lat, lng, source, label}`, or `{name, error}` when it can't be
    found, with `transient` when a lookup failed rather than found nothing."""
    query = anchor_query(near, location)
    transient = False
    try:
        point = await geocode(query)
    except Exception:
        logger.info("research anchor geocode failed", exc_info=True)
        point, transient = None, True
    if point is not None:
        return {"name": near, "lat": point[0], "lng": point[1], "source": "census", "label": query}
    town = town_point(near, location)
    if town is not None:
        label, (lat, lng) = town
        return {"name": near, "lat": lat, "lng": lng, "source": "gazetteer", "label": label}
    failed = {"name": near, "error": f"Couldn't find {near} on a map, so distances from it are unknown."}
    return {**failed, "transient": True} if transient else failed


async def from_address(fields: dict, anchor: dict, *, geocode: Geocode) -> dict:
    """Distance and direction from the finding's stored address, or {}."""
    address = (fields or {}).get("address")
    if not isinstance(address, dict) or address.get("status") not in F.STATUS_RANK:
        return {}
    line = F.clean_text(address.get("value"), 200)
    # The Census geocoder needs a street number to place an address.
    if not any(ch.isdigit() for ch in line):
        return {}
    try:
        point = await geocode(line)
    except Exception:
        logger.info("research address geocode failed", exc_info=True)
        return {}
    if point is None:
        return {}
    return distance_fields(point, anchor, status=address["status"], origin="geocode",
                           url=(address.get("evidence") or {}).get("url"), how=f"{line}, by the US Census geocoder")
