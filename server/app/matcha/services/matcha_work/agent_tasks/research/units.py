"""An apartment building's homes for rent, one by one. No model.

Large buildings publish what they have to let through a leasing system, and
two answer a plain request:

  SightMap  the unit map embedded on many buildings' sites (Brookfield,
            Essex, Jonah-built sites and others). Its embed page names its
            API, which lists every home with its rent, move-in date, lease
            term, specials and floor plan.
  Avalon    avaloncommunities.com: the community's own API, with its
            promotions and each home's page.

Every figure is the leasing system's own (origin `leasing`, which outranks a
page's schema.org data: it is per home and current). A home's net rent is
worked out only from a special that says how much is free (`net_rent`); "up
to" isn't a promise, so it gives none.

`find_units` returns None when the page names neither system or its answer
can't be read, and the building's floor plans are read as before. A home's
floor plan is kept as `plan_source` (never shown) until `phases.rehost_plans`
puts it on our CDN as `plan_image`.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from app.matcha.services.matcha_work.agent_card.page_extract import site_of

from . import fields as F

logger = logging.getLogger(__name__)

# Homes kept per building, cheapest first: a big building has a hundred.
MAX_UNITS = 80
ORIGIN = "leasing"
_RENT_RANGE = (100.0, 50_000.0)

_SIGHTMAP_EMBED = re.compile(r"https?://sightmap\.com/embed/(?!api\b)([a-z0-9]{6,20})\b")
_SIGHTMAP_API = re.compile(r"https://sightmap\.com/app/api/v1/[A-Za-z0-9]+/sightmaps/\d+")
_AVALON_ID = re.compile(r"""communityId['"]?\s*:\s*['"]AVB-([A-Z]{2}\d{3})['"]""")
_AVALON_UNIT = re.compile(r"/apartment/([A-Z]{2}\d{3})-")
AVALON_API = "https://api.avalonbay.com/json/reply/ApartmentSearch?communityCode={code}"
_UNIT_KEY = re.compile(r"[A-Z0-9\-]{4,40}")
_LEASE_TERM = re.compile(r"(\d{1,2})\s*(?:months?|mos?\.?)\b", re.I)

# Loads a URL for this building (counted against the round's page loads):
# the body, or None when it couldn't be read.
Load = Callable[[str, bool], Awaitable[bytes | None]]


def lowest_rent(unit: dict) -> float:
    """What a home costs a month at least: its net rent after a stated
    special, else its rent."""
    return min(unit.get("net_rent") or unit["rent"], unit["rent"])


@dataclass(frozen=True)
class Found:
    units: list[dict]
    # Offers for the whole building ("$250 deposit when you apply by 10-31").
    promotions: list[str]
    source: str
    # The page the homes were read for (the building's page or its floor plans).
    url: str


def _page(url: str) -> str:
    """A page's address without its port, query or fragment ("…:443/?utm_…")."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}{parts.path or '/'}" if parts.hostname else url


def _text(raw: bytes | str) -> str:
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or "")
    return text.replace("\\/", "/")  # embed URLs inside JSON


def sightmap_embed(raw: bytes | str) -> str | None:
    """The building's SightMap embed id, named anywhere in its page."""
    match = _SIGHTMAP_EMBED.search(_text(raw))
    return match.group(1) if match else None


def avalon_code(raw: bytes | str, url: str) -> str | None:
    """An Avalon community's code ("CA104"), from its own page only."""
    if site_of(urlsplit(url).hostname or "") != "avaloncommunities.com":
        return None
    text = _text(raw)
    match = _AVALON_ID.search(text) or _AVALON_UNIT.search(text)
    return match.group(1) if match else None


def _number(raw: Any) -> float | None:
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = float(str(raw).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None
    return value if value == value else None  # NaN


def _rent(raw: Any) -> float | None:
    value = _number(raw)
    return value if value is not None and _RENT_RANGE[0] <= value <= _RENT_RANGE[1] else None


def _iso(raw: Any, today: date) -> str | None:
    """A move-in date; one already past is today (it's available now)."""
    try:
        day = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None
    return max(day, today).isoformat()


def _months(raw: Any) -> int | None:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return int(raw) if 1 <= raw <= 36 else None
    match = _LEASE_TERM.search(str(raw or ""))
    return int(match.group(1)) if match and 1 <= int(match.group(1)) <= 36 else None


# ── net rent ─────────────────────────────────────────────────────────────────

_FEW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        "nine": 9, "ten": 10, "twelve": 12}
_FREE = re.compile(
    r"\b(?P<n>\d{1,2}|" + "|".join(_FEW) + r")\s*(?P<what>weeks?|months?)\s+(?:of\s+)?(?:rent\s+)?free\b"
    r"|\b(?P<first>first|1st)\s+month(?:'s)?\s+(?:rent\s+)?free\b|\bfree\s+(?:first\s+)?month(?:'s)?\s+rent\b",
    re.I,
)
_UP_TO = re.compile(r"\bup\s+to\s*$", re.I)
_LEASE_IN_TEXT = re.compile(r"\b(\d{1,2})\s*\+?\s*[- ]?\s*(?:months?|mo\.?)\s*(?:lease|term)\b", re.I)
DEFAULT_LEASE = 12
_WEEKS_A_MONTH = 52 / 12


def net_rent(rent: float, special: str | None, lease_months: int | None) -> tuple[float, str] | None:
    """What a home costs a month over its lease after a "N weeks/months free"
    special, and how that was worked out. None when the special frees no
    stated amount ("up to 8 weeks" is a ceiling, not a promise)."""
    text = " ".join(str(special or "").split())
    match = _FREE.search(text)
    if match is None or _UP_TO.search(text[:match.start()]):
        return None
    if match.group("n"):
        n = match.group("n").lower()
        count = float(_FEW.get(n) or int(n))
        free = count / _WEEKS_A_MONTH if match.group("what").lower().startswith("week") else count
    else:
        free = 1.0
    stated = _LEASE_IN_TEXT.search(text)
    lease = int(stated.group(1)) if stated else lease_months
    assumed = lease is None
    lease = lease or DEFAULT_LEASE
    if not 0 < free < lease:
        return None
    net = round(rent * (lease - free) / lease)
    phrase = " ".join(match.group(0).split())
    how = f"{phrase} on a {lease}-month lease" + (" (lease length assumed)" if assumed else "")
    return float(net), how


# ── reading the leasing systems ──────────────────────────────────────────────

def _unit(*, uid: str, number: str, floor: Any, plan: str, beds: Any, baths: Any, sqft: Any, rent: float,
          available: str | None, lease: int | None, special: str, plan_image: str | None,
          tour: str | None, url: str | None, source: str) -> dict:
    out = {
        "id": uid, "number": F.clean_text(number, 20), "floor": F.clean_text(floor, 10) if floor not in (None, "") else None,
        "plan": F.clean_text(plan, 40) or None,
        "beds": _number(beds), "baths": _number(baths), "sqft": _number(sqft),
        "rent": rent, "currency": "USD", "available": available, "lease_months": lease,
        "special": F.clean_text(special, 200) or None,
        "plan_image": None,
        "plan_source": plan_image if isinstance(plan_image, str) and plan_image.startswith("https://") else None,
        "tour_url": tour if isinstance(tour, str) and tour.startswith("https://") else None,
        # Its own page, where it has one (Avalon's); a unit map's homes share the building's.
        "url": url, "source": source,
    }
    netted = net_rent(rent, out["special"], lease)
    if netted is not None and netted[0] < rent:
        out["net_rent"], out["net_note"] = netted
    return out


def _plan_name(plan: dict) -> str:
    raw = plan.get("name")
    if isinstance(raw, str) and raw.startswith("{"):
        try:
            raw = (json.loads(raw) or {}).get("name")
        except (ValueError, AttributeError):
            raw = None
    return str(raw or plan.get("filter_label") or "")


def sightmap_units(payload: dict, *, today: date) -> list[dict]:
    """Every home a SightMap lists with a rent. A map can list a building's
    homes without rents (Avalon's does): those say nothing about what's to let."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    floors = {str(f.get("id")): f.get("filter_short_label") or f.get("filter_label")
              for f in data.get("floors") or [] if isinstance(f, dict)}
    plans = {str(p.get("id")): p for p in data.get("floor_plans") or [] if isinstance(p, dict)}
    out = []
    for raw in data.get("units") or []:
        if not isinstance(raw, dict):
            continue
        rent = _rent(raw.get("price"))
        if rent is None:
            continue
        plan = plans.get(str(raw.get("floor_plan_id"))) or {}
        available = _iso(raw.get("available_on"), today)
        if available is None and "now" in str(raw.get("display_available_on") or "").lower():
            available = today.isoformat()
        tour = next((link.get("url") for link in raw.get("outbound_links") or []
                     if isinstance(link, dict) and ("tour" in str(link.get("icon_type") or "")
                                                    or "tour" in str(link.get("label") or "").lower())), None)
        out.append(_unit(
            uid=f"sightmap:{raw.get('id')}", number=str(raw.get("unit_number") or raw.get("label") or ""),
            floor=floors.get(str(raw.get("floor_id"))), plan=_plan_name(plan),
            beds=plan.get("bedroom_count"), baths=plan.get("bathroom_count"), sqft=raw.get("area"),
            rent=rent, available=available, lease=_months(raw.get("display_lease_term")),
            special=str(raw.get("specials_description") or ""), plan_image=plan.get("image_url"),
            tour=tour, url=None, source="sightmap",
        ))
    return out


def avalon_units(payload: dict, *, url: str, today: date) -> tuple[list[dict], list[str]]:
    """An Avalon community's homes to let, and its promotions."""
    results = payload.get("results") if isinstance(payload.get("results"), dict) else payload
    promotions = [F.clean_text(p.get("promotionTitle"), 200) for p in results.get("communityPromotions") or []
                  if isinstance(p, dict) and p.get("promotionTitle")]
    base = _page(url)
    base = base if base.endswith("/") else base + "/"
    out, seen = [], set()
    for kind in results.get("availableFloorPlanTypes") or []:
        for plan in (kind or {}).get("availableFloorPlans") or []:
            if not isinstance(plan, dict):
                continue
            homes = list(plan.get("apartments") or [])
            for package in plan.get("finishPackages") or []:
                homes.extend((package or {}).get("apartments") or [])
            for home in homes:
                if not isinstance(home, dict):
                    continue
                key = str(home.get("unitKey") or "")
                if not _UNIT_KEY.fullmatch(key):
                    # No key of its own: known by its number, never by "None".
                    number = F.clean_text(home.get("apartmentNumber"), 20)
                    if not number:
                        continue
                    key = f"{plan.get('floorPlanName') or ''}#{number}"
                if key in seen:
                    continue
                pricing = home.get("pricing") or {}
                rent = _rent(pricing.get("effectiveRent") or pricing.get("amenitizedRent"))
                if rent is None or pricing.get("showAsAvailable") is False:
                    continue
                seen.add(key)
                titles = [p.get("promotionTitle") for p in home.get("promotions") or []
                          if isinstance(p, dict) and p.get("promotionTitle")]
                unit = _unit(
                    uid=f"avalon:{key}", number=str(home.get("apartmentNumber") or ""),
                    floor=home.get("floor"), plan=str(plan.get("floorPlanName") or ""),
                    beds=home.get("beds"), baths=home.get("baths"), sqft=home.get("apartmentSize"),
                    rent=rent, available=_iso(pricing.get("availableDate"), today),
                    lease=_months(pricing.get("term")), special="; ".join(titles),
                    plan_image=plan.get("floorPlanImage"), tour=None,
                    url=f"{base}apartment/{key}/" if _UNIT_KEY.fullmatch(key) else None,
                    source="avalon",
                )
                net = _rent(pricing.get("netEffectiveRent"))
                if net is not None and net < rent and "net_rent" not in unit:
                    unit["net_rent"], unit["net_note"] = net, "Avalon's net effective rent"
                out.append(unit)
    return out, promotions


def _cheapest(units: list[dict]) -> list[dict]:
    return sorted(units, key=lambda u: (lowest_rent(u), u["rent"], u["number"]))[:MAX_UNITS]


async def find_units(raw: bytes, url: str, load: Load, *, today: date, tried: set[str] | None = None) -> Found | None:
    """A building's homes from the leasing system its page names, or None.
    `tried` holds the systems already asked for this building (its own page
    and its floor plans page often name the same one): never asked twice."""
    tried = set() if tried is None else tried
    code = avalon_code(raw, url)
    if code is not None and f"avalon:{code}" not in tried:
        tried.add(f"avalon:{code}")
        url = _page(url)
        body = await load(AVALON_API.format(code=code), True)
        units, promotions = _parse(body, lambda p: avalon_units(p, url=url, today=today), ([], []))
        if units:
            return Found(_cheapest(units), promotions, "avalon", url)
    embed = sightmap_embed(raw)
    if embed is None or f"sightmap:{embed}" in tried:
        return None
    tried.add(f"sightmap:{embed}")
    page = await load(f"https://sightmap.com/embed/{embed}", False)
    api = _SIGHTMAP_API.search(_text(page or b""))
    if api is None:
        return None
    body = await load(api.group(0), True)
    units = _parse(body, lambda p: sightmap_units(p, today=today), [])
    return Found(_cheapest(units), [], "sightmap", url) if units else None


def _parse(body: bytes | None, read: Callable[[dict], Any], empty: Any) -> Any:
    if not body:
        return empty
    try:
        payload = json.loads(body)
        return read(payload) if isinstance(payload, dict) else empty
    except (ValueError, TypeError, AttributeError, KeyError):
        logger.info("research units: a leasing system's answer could not be read", exc_info=True)
        return empty


# ── what a building's homes say about the building ───────────────────────────

def building_fields(found: Found, *, today: date) -> dict:
    """The building's rent (every home's), soonest move-in and specials, as
    stored fields from the leasing system. Limits are checked on the homes
    themselves (`ranking.unit_verdict`); these are what the list shows."""
    units = found.units
    out: dict[str, dict] = {}
    rents = sorted({u["rent"] for u in units})
    cheapest = min(units, key=lambda u: u["rent"])
    price = F.entry(F.LIBRARY["price"], rents[0], status="verified", origin=ORIGIN, today=today,
                    url=found.url, unit="month", quote=unit_line(cheapest))
    if price is not None:
        price["spans"] = [[lowest_rent(u), u["rent"]] for u in units][:F.MAX_SPANS]
        if rents[-1] > rents[0]:
            spec = F.LIBRARY["price"]
            price["high"] = rents[-1]
            price["display"] = (f"{F.display(spec, rents[0], currency='USD')}–"
                                f"{F.display(spec, rents[-1], currency='USD')}/mo")
        out["price"] = price
    soonest = min((u for u in units if u.get("available")), key=lambda u: u["available"], default=None)
    if soonest is not None:
        made = F.entry(F.LIBRARY["available_date"], soonest["available"], status="verified", origin=ORIGIN,
                       today=today, url=found.url, quote=unit_line(soonest))
        if made is not None:
            out["available_date"] = made
    special = next(iter(found.promotions), None) or next((u["special"] for u in units if u.get("special")), None)
    if special:
        made = F.entry(F.LIBRARY["specials"], special, status="verified", origin=ORIGIN, today=today,
                       url=found.url, quote=special)
        if made is not None:
            out["specials"] = made
    return out


def unit_line(unit: dict) -> str:
    """One home as a line a model or a document reads."""
    parts = [f"#{unit['number']}" if unit.get("number") else "a home"]
    if unit.get("floor"):
        parts.append(f"floor {unit['floor']}")
    beds = unit.get("beds")
    if beds is not None:
        parts.append("studio" if beds == 0 else f"{beds:g} bd")
    if unit.get("baths") is not None:
        parts.append(f"{unit['baths']:g} ba")
    if unit.get("sqft"):
        parts.append(f"{unit['sqft']:,.0f} sq ft")
    parts.append(f"${unit['rent']:,.0f}/mo")
    if unit.get("net_rent"):
        parts.append(f"${unit['net_rent']:,.0f}/mo net ({unit.get('net_note')})")
    if unit.get("available"):
        parts.append(f"available {unit['available']}")
    if unit.get("special"):
        parts.append(f"special: {unit['special']}")
    return ", ".join(parts)
