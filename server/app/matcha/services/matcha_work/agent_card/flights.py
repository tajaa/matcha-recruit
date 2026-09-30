"""Flight search for agent cards, through the Duffel API.

Why an API and not the web: airline and Google Flights pages need JavaScript
and block bots, so `fetch_page` never sees a fare. Duffel returns airlines' own
offers as data.

Private by construction: the search runs on our server and sends only the
itinerary (airports, dates, passenger count, cabin, bags to price). Nothing
about the person — location, device, browser, cookies, account, search
history — is sent, so none of it can move the price. `privacy_disclosure()`
puts exactly that on the result.

The cheaper-fare work is done here, deterministically, within a fixed request
budget and time budget: flexible dates, nearby airports, round trips also
priced as two one-way tickets, and a total that includes the bags the person
needs. Warnings (tight connections, overnight layovers, basic economy, separate
tickets, a different airport or date) are computed here too.

The model never states a fare. It picks offers by id; `schema` rebuilds every
price, time, flight number, bag count and warning from `FlightSession`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TOKEN_ENV = "DUFFEL_ACCESS_TOKEN"
API_BASE = "https://api.duffel.com"
API_VERSION = "v2"

MAX_OFFER_REQUESTS = 16  # per run, across every search_flights call
# One call can't spend the whole run, so a refining search is still possible.
MAX_REQUESTS_PER_SEARCH = 10
MAX_CONCURRENT_REQUESTS = 4
MAX_OFFER_FETCHES = 6  # per call: offers re-read to price bags ("true total")
SUPPLIER_TIMEOUT_MS = 15_000
HTTP_TIMEOUT_SECONDS = 25.0
# Time budget of one call. Whatever finishes inside it is kept; requests
# still waiting when it runs out are cancelled and given back to the budget.
SEARCH_SECONDS = 100.0
NEARBY_SECONDS = 10.0
BAG_SECONDS = 15.0  # held back from the offer requests for bag pricing
MAX_OFFERS_KEPT_PER_REQUEST = 40
MAX_OPTIONS_STORED = 80
MAX_TOOL_OPTIONS = 15
MAX_LEGS_PAIRED = 5
NEARBY_RADIUS_METRES = 160_000  # ~100 miles
MAX_NEARBY_AIRPORTS = 2
MAX_PASSENGERS = 6
MAX_FLEX_DAYS = 2
MAX_DAYS_AHEAD = 330
CABINS = ("economy", "premium_economy", "business", "first")
# Ages Duffel prices children and lap infants by; the request never asks for
# anyone's real age.
_CHILD_AGE, _INFANT_AGE = 8, 1

# A trip, said so plainly: "flights to Denver", "fly to Denver", "airfare",
# "one-way tickets", "round trip to Lisbon" (never "a JSON round-trip to
# disk" or "flights from the queue"). Enough on its own to make a chat message
# an errand.
_TRIP = re.compile(
    r"\bflights?\s+(?:to|from|into|between)\s+(?-i:[A-Z])"
    r"|\bfly(?:ing)?\s+(?:to|from|into|out\s+of|between|home|back)\b"
    r"|\b(?:air\s?fares?|(?:plane|airline)\s+(?:tickets?|fares?))\b"
    r"|\b(?:round[- ]trip|one[- ]way|non-?stop|direct)\s+(?:flights?|tickets?|fares?)\b"
    r"|\b(?:round[- ]trip|non-?stop)\s+(?:to|from)\s+(?-i:[A-Z])",
    re.IGNORECASE,
)
# On a card someone made to be researched, "flight" alone is a trip too
# ("cheapest flight SFO to JFK"), unless it's one of the other flights:
# "employee flight risk", "a wine flight", "flight simulator". Bare "fly",
# "one-way" and "nonstop" never count ("fly fishing rod", "one-way valve").
_FLIGHT_WORD = re.compile(
    r"(?<!wine )(?<!beer )(?<!tasting )\bflights?\b"
    r"(?!\s+(?:risks?|of|mode|sim(?:ulator)?s?|controllers?|jackets?|decks?|suits?|sticks?|cases?|"
    r"recorders?|schools?|instructors?|attendants?|logs?)\b)",
    re.IGNORECASE,
)
_IATA = re.compile(r"^[A-Z]{3}$")
_ISO_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$")

SEPARATE_TICKETS_WARNING = (
    "Two separate tickets: each airline only handles changes, delays and cancellations on its own ticket."
)


def token() -> str | None:
    value = (os.getenv(TOKEN_ENV) or "").strip()
    return value or None


def enabled() -> bool:
    return token() is not None


def is_trip(text: str) -> bool:
    """An unmistakable trip request: what makes a chat message a travel errand."""
    return bool(_TRIP.search(text or ""))


def is_travel_ask(text: str) -> bool:
    """Whether an agent card is about flights (gets `search_flights`)."""
    return is_trip(text) or bool(_FLIGHT_WORD.search(text or ""))


def privacy_disclosure() -> dict:
    """What the search sent, and what it didn't. Server text, never the model's."""
    return {
        "via": "Matcha's server, through the Duffel API",
        "sent": ["airports", "dates", "number of passengers", "cabin", "bags to price"],
        "not_sent": [
            "your location", "your device or browser", "cookies", "your account", "your search history",
        ],
    }


class FlightError(ValueError):
    """A search the tool refuses; the message goes back to the model."""


class DuffelError(RuntimeError):
    pass


@dataclass(frozen=True)
class FlightQuery:
    origin: str
    destination: str
    depart: date
    return_date: date | None
    adults: int = 1
    children: int = 0
    infants: int = 0
    cabin: str = "economy"
    max_connections: int = 1
    flexible_days: int = 0
    nearby_airports: bool = False
    checked_bags: int = 0
    carry_on_bags: int = 0

    @property
    def round_trip(self) -> bool:
        return self.return_date is not None

    def passengers(self) -> list[dict]:
        return (
            [{"type": "adult"}] * self.adults
            + [{"age": _CHILD_AGE}] * self.children
            + [{"age": _INFANT_AGE}] * self.infants
        )

    def summary(self) -> str:
        trip = f"{self.origin} → {self.destination}, {self.depart:%b %-d}"
        if self.return_date:
            trip += f" – {self.return_date:%b %-d}"
        people = self.adults + self.children + self.infants
        parts = [trip, f"{people} passenger{'s' if people != 1 else ''}", self.cabin.replace("_", " ")]
        if self.checked_bags:
            parts.append(f"{self.checked_bags} checked bag{'s' if self.checked_bags != 1 else ''} each")
        if self.flexible_days:
            parts.append(f"±{self.flexible_days} day{'s' if self.flexible_days != 1 else ''}")
        if self.nearby_airports:
            parts.append("nearby airports")
        return ", ".join(parts)


def _int(value: Any, default: int, low: int, high: int, name: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise FlightError(f"{name} must be a whole number")
    if not low <= int(value) <= high:
        raise FlightError(f"{name} must be between {low} and {high}")
    return int(value)


def _date(value: Any, name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise FlightError(f"{name} must be a date like 2026-11-12") from exc


def parse_query(args: dict, *, today: date) -> FlightQuery:
    origin = str(args.get("origin") or "").strip().upper()
    destination = str(args.get("destination") or "").strip().upper()
    if not _IATA.match(origin) or not _IATA.match(destination):
        raise FlightError("origin and destination must be 3-letter IATA codes (SFO, or a city code like NYC)")
    if origin == destination:
        raise FlightError("origin and destination are the same")
    depart = _date(args.get("depart_date"), "depart_date")
    return_date = _date(args["return_date"], "return_date") if args.get("return_date") else None
    if depart < today:
        raise FlightError("depart_date is in the past")
    if depart > today + timedelta(days=MAX_DAYS_AHEAD):
        raise FlightError(f"airlines only sell about {MAX_DAYS_AHEAD} days ahead")
    if return_date and return_date < depart:
        raise FlightError("return_date is before depart_date")
    if return_date and return_date > today + timedelta(days=MAX_DAYS_AHEAD):
        raise FlightError(f"airlines only sell about {MAX_DAYS_AHEAD} days ahead")
    adults = _int(args.get("adults"), 1, 1, MAX_PASSENGERS, "adults")
    children = _int(args.get("children"), 0, 0, MAX_PASSENGERS, "children")
    infants = _int(args.get("infants"), 0, 0, adults, "infants")  # one lap infant per adult
    if adults + children + infants > MAX_PASSENGERS:
        raise FlightError(f"at most {MAX_PASSENGERS} passengers")
    cabin = str(args.get("cabin") or "economy").strip().lower()
    if cabin not in CABINS:
        raise FlightError(f"cabin must be one of {', '.join(CABINS)}")
    return FlightQuery(
        origin=origin, destination=destination, depart=depart, return_date=return_date,
        adults=adults, children=children, infants=infants, cabin=cabin,
        max_connections=_int(args.get("max_connections"), 1, 0, 2, "max_connections"),
        flexible_days=_int(args.get("flexible_days"), 0, 0, MAX_FLEX_DAYS, "flexible_days"),
        nearby_airports=bool(args.get("nearby_airports")),
        checked_bags=_int(args.get("checked_bags"), 0, 0, 3, "checked_bags"),
        carry_on_bags=_int(args.get("carry_on_bags"), 0, 0, 1, "carry_on_bags"),
    )


# ── search plan ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Variant:
    """One offer request. `leg` is None for a normal search, or "out"/"back"
    for one half of a round trip priced as its own one-way ticket."""
    slices: tuple[tuple[str, str, date], ...]
    date_shift: tuple[int, ...]
    airports_changed: bool
    leg: str | None = None


def plan_variants(
    q: FlightQuery, *, origins: list[str], destinations: list[str], budget: int, today: date,
) -> tuple[list[Variant], dict[str, int]]:
    """The offer requests to run, at most `budget`, and how many were left
    out. First the exact trip and, for a round trip, each direction as its
    own one-way ticket. Then other dates and other airports (on the exact
    dates) take turns, nearest date first and one changed airport before two,
    so a tight budget still tries some of each."""
    def trip(o: str, d: str, out_shift: int, back_shift: int) -> tuple[tuple[str, str, date], ...]:
        legs = [(o, d, q.depart + timedelta(days=out_shift))]
        if q.return_date:
            legs.append((d, o, q.return_date + timedelta(days=back_shift)))
        return tuple(legs)

    def valid(v: Variant) -> bool:
        dates = [s[2] for s in v.slices]
        return dates[0] >= today and dates == sorted(dates)

    exact_shift = (0, 0) if q.round_trip else (0,)
    core = [Variant(trip(q.origin, q.destination, 0, 0), exact_shift, False)]
    if q.round_trip:
        exact = core[0].slices
        core += [Variant((exact[0],), (0,), False, leg="out"), Variant((exact[1],), (0,), False, leg="back")]
    flex = range(-q.flexible_days, q.flexible_days + 1)
    if q.round_trip:
        shifts = sorted(
            ((a, b) for a in flex for b in flex if (a, b) != (0, 0)),
            key=lambda s: (abs(s[0]) + abs(s[1]), abs(s[0]), s),
        )
    else:
        shifts = sorted(((a,) for a in flex if a != 0), key=lambda s: (abs(s[0]), s))
    dated = [
        v for v in (
            Variant(trip(q.origin, q.destination, s[0], s[1] if q.round_trip else 0), s, False) for s in shifts
        ) if valid(v)
    ]
    pairs = [
        (o, d) for o in origins for d in destinations
        if o != d and (o, d) != (q.origin, q.destination)
    ]
    pairs.sort(key=lambda p: (p[0] != q.origin) + (p[1] != q.destination))  # stable: nearby order kept
    moved = [v for v in (Variant(trip(o, d, 0, 0), exact_shift, True) for o, d in pairs) if valid(v)]

    plan = [v for v in core if valid(v)][:budget]
    turns: list[Variant] = []
    for i in range(max(len(dated), len(moved))):
        turns += dated[i:i + 1] + moved[i:i + 1]
    chosen = turns[:max(0, budget - len(plan))]
    skipped = {
        "other_dates": len(dated) - sum(not v.airports_changed for v in chosen),
        "other_airports": len(moved) - sum(v.airports_changed for v in chosen),
    }
    return plan + chosen, skipped


# ── Duffel ────────────────────────────────────────────────────────────────────

class DuffelClient:
    def __init__(self, access_token: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Duffel-Version": API_VERSION,
                "Accept": "application/json",
            },
            timeout=HTTP_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, path: str, **kwargs) -> Any:
        for attempt in range(2):
            response = await self._client.request(method, path, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue
            if response.status_code >= 400:
                try:
                    errors = response.json().get("errors") or []
                    message = errors[0].get("message") or errors[0].get("title")
                except (ValueError, AttributeError, IndexError):
                    message = None
                raise DuffelError(message or f"Duffel answered HTTP {response.status_code}")
            return response.json().get("data")
        raise DuffelError("Duffel is busy; try again shortly")  # pragma: no cover - loop always returns

    async def offer_request(self, variant: Variant, q: FlightQuery) -> list[dict]:
        data = await self._call(
            "POST", "/air/offer_requests",
            params={"return_offers": "true", "supplier_timeout": SUPPLIER_TIMEOUT_MS},
            json={"data": {
                "slices": [
                    {"origin": o, "destination": d, "departure_date": day.isoformat()}
                    for o, d, day in variant.slices
                ],
                "passengers": q.passengers(),
                "cabin_class": q.cabin,
                "max_connections": q.max_connections,
            }},
        )
        return list((data or {}).get("offers") or [])

    async def offer(self, offer_id: str) -> dict:
        return await self._call(
            "GET", f"/air/offers/{offer_id}", params={"return_available_services": "true"},
        ) or {}

    async def places(self, **params) -> list[dict]:
        return list(await self._call("GET", "/places/suggestions", params=params) or [])


# ── offers → options ──────────────────────────────────────────────────────────

def _money(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _minutes(iso: Any) -> int | None:
    match = _ISO_DURATION.match(str(iso or ""))
    if not match or not any(match.groups()):
        return None
    days, hours, minutes = (int(g or 0) for g in match.groups())
    return days * 1440 + hours * 60 + minutes


def _when(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _lap_infant(passenger: dict) -> bool:
    """A lap infant: no seat and no bags of their own. Duffel may return the
    type, or only the age we sent (lap infants go as age 1)."""
    kind = passenger.get("type")
    if kind == "infant_without_seat":
        return True
    age = passenger.get("age")
    return not kind and isinstance(age, int) and not isinstance(age, bool) and age < 2


def _bags_included(offer: dict) -> dict:
    """Bags every seated passenger has on every segment (the minimum across
    them). A lap infant has none, so counting them would make every fare look
    bagless and charge the adult for bags the fare already includes."""
    infants = {str(p.get("id")) for p in offer.get("passengers") or [] if _lap_infant(p)}
    checked: list[int] = []
    carry_on: list[int] = []
    for sl in offer.get("slices") or []:
        for seg in sl.get("segments") or []:
            for pax in seg.get("passengers") or []:
                if str(pax.get("passenger_id")) in infants:
                    continue
                bags = {b.get("type"): int(b.get("quantity") or 0) for b in pax.get("baggages") or []}
                checked.append(bags.get("checked", 0))
                carry_on.append(bags.get("carry_on", 0))
    return {"checked": min(checked) if checked else 0, "carry_on": min(carry_on) if carry_on else 0}


def _condition(offer: dict, key: str) -> bool | None:
    value = (offer.get("conditions") or {}).get(key)
    if isinstance(value, dict) and isinstance(value.get("allowed"), bool):
        return value["allowed"]
    return None


def offer_option(offer: dict, variant: Variant) -> dict | None:
    """One Duffel offer as a result option, or None if it's malformed."""
    try:
        slices = []
        for sl in offer["slices"]:
            segments = []
            for seg in sl["segments"]:
                carrier = seg.get("marketing_carrier") or {}
                code = carrier.get("iata_code") or ""
                segments.append({
                    "carrier": carrier.get("name") or code,
                    "flight_number": f"{code} {seg.get('marketing_carrier_flight_number') or ''}".strip(),
                    "origin": seg["origin"]["iata_code"],
                    "destination": seg["destination"]["iata_code"],
                    "departing_at": seg["departing_at"],
                    "arriving_at": seg["arriving_at"],
                    "duration_minutes": _minutes(seg.get("duration")),
                })
            if not segments:
                return None
            slices.append({
                "origin": segments[0]["origin"],
                "destination": segments[-1]["destination"],
                "departing_at": segments[0]["departing_at"],
                "arriving_at": segments[-1]["arriving_at"],
                "duration_minutes": _minutes(sl.get("duration")),
                "stops": len(segments) - 1,
                "fare_brand": sl.get("fare_brand_name") or None,
                "segments": segments,
            })
        total = _money(offer["total_amount"])
        if total is None or not slices:
            return None
        owner = offer.get("owner") or {}
        return {
            "id": str(offer["id"]),
            "ticketing": "single",
            "total_amount": str(total),
            "currency": str(offer.get("total_currency") or "").upper(),
            "true_total_amount": None,
            "bag_note": None,
            "owner": owner.get("name") or owner.get("iata_code") or "",
            "carriers": sorted({s["carrier"] for sl in slices for s in sl["segments"] if s["carrier"]}),
            "slices": slices,
            "bags_included": _bags_included(offer),
            "conditions": {
                "refundable": _condition(offer, "refund_before_departure"),
                "changeable": _condition(offer, "change_before_departure"),
            },
            "expires_at": offer.get("expires_at"),
            "date_shift_days": list(variant.date_shift),
            "airports_changed": variant.airports_changed,
            "leg_ids": [str(offer["id"])],
            "warnings": [],
        }
    except (KeyError, TypeError, IndexError):
        return None


def combine(out: dict, back: dict) -> dict | None:
    """A round trip as two one-way tickets. Never across currencies."""
    if out["currency"] != back["currency"]:
        return None
    changeable = [out["conditions"]["changeable"], back["conditions"]["changeable"]]
    refundable = [out["conditions"]["refundable"], back["conditions"]["refundable"]]

    def both(values):
        return None if None in values else all(values)

    return {
        **out,
        "id": f"combo:{out['id']}+{back['id']}",
        "ticketing": "separate",
        "total_amount": str(Decimal(out["total_amount"]) + Decimal(back["total_amount"])),
        "owner": out["owner"] if out["owner"] == back["owner"] else f"{out['owner']} + {back['owner']}",
        "carriers": sorted(set(out["carriers"]) | set(back["carriers"])),
        "slices": out["slices"] + back["slices"],
        "bags_included": {
            k: min(out["bags_included"][k], back["bags_included"][k]) for k in ("checked", "carry_on")
        },
        "conditions": {"refundable": both(refundable), "changeable": both(changeable)},
        "expires_at": min(filter(None, [out["expires_at"], back["expires_at"]]), default=None),
        "date_shift_days": out["date_shift_days"] + back["date_shift_days"],
        "airports_changed": out["airports_changed"] or back["airports_changed"],
        "leg_ids": out["leg_ids"] + back["leg_ids"],
        "warnings": [],
    }


def _signature(option: dict) -> tuple:
    return (
        option["ticketing"],
        tuple((s["flight_number"], s["departing_at"]) for sl in option["slices"] for s in sl["segments"]),
    )


def bag_cost(offer: dict, *, bag_type: str, quantity: int) -> Decimal | None:
    """What `quantity` extra bags of `bag_type` per passenger cost on this
    offer, from its listed bag services, or None when they can't be priced.
    Lap infants carry no bags of their own."""
    if quantity <= 0:
        return Decimal(0)
    currency = str(offer.get("total_currency") or "").upper()
    services = [
        s for s in offer.get("available_services") or []
        if s.get("type") == "baggage"
        and ((s.get("metadata") or {}).get("type") or "checked") == bag_type
        and int(s.get("maximum_quantity") or 0) >= quantity
        and str(s.get("total_currency") or "").upper() == currency
        and _money(s.get("total_amount")) is not None
    ]
    slice_segments = [
        frozenset(seg["id"] for seg in sl.get("segments") or [] if seg.get("id"))
        for sl in offer.get("slices") or []
    ]
    if not slice_segments or not all(slice_segments):
        return None
    journey = frozenset().union(*slice_segments)
    total = Decimal(0)
    for pax in offer.get("passengers") or []:
        if _lap_infant(pax):
            continue
        mine = [s for s in services if pax.get("id") in (s.get("passenger_ids") or [])]

        def cheapest(segments: frozenset) -> Decimal | None:
            prices = [_money(s["total_amount"]) for s in mine if frozenset(s.get("segment_ids") or []) == segments]
            return min(prices) if prices else None

        choices = []
        per_slice = [cheapest(segs) for segs in slice_segments]
        if all(p is not None for p in per_slice):
            choices.append(sum(per_slice, Decimal(0)))
        whole = cheapest(journey)
        if whole is not None:
            choices.append(whole)
        if not choices:
            return None
        total += min(choices) * quantity
    return total


def _layover_warnings(option: dict) -> list[str]:
    # Separate tickets split the trip by direction, so every connection is
    # still inside one ticket and keeps the airline's connection protection.
    out = []
    for sl in option["slices"]:
        segments = sl["segments"]
        for prev, nxt in zip(segments, segments[1:]):
            arrive, depart = _when(prev["arriving_at"]), _when(nxt["departing_at"])
            if not arrive or not depart:
                continue
            minutes = int((depart - arrive).total_seconds() // 60)
            airport = prev["destination"]
            if minutes < 60:
                out.append(f"Tight {minutes} min connection in {airport}")
            elif depart.date() > arrive.date() or (minutes >= 240 and (arrive.hour >= 22 or depart.hour < 6)):
                out.append(f"Overnight layover in {airport}")
            elif minutes >= 360:
                out.append(f"Long {minutes // 60}h layover in {airport}")
    return out


def warnings_for(option: dict, q: FlightQuery) -> list[str]:
    out = []
    if option["ticketing"] == "separate":
        out.append(SEPARATE_TICKETS_WARNING)
    out += _layover_warnings(option)
    brands = " ".join(sl.get("fare_brand") or "" for sl in option["slices"]).lower()
    if "basic" in brands:
        out.append("Basic economy: usually no seat choice and no changes")
    elif option["conditions"]["changeable"] is False:
        out.append("This fare can't be changed")
    if q.carry_on_bags and option["bags_included"]["carry_on"] < q.carry_on_bags:
        out.append("Carry-on bag not included in the fare")
    if option["airports_changed"]:
        first = option["slices"][0]
        out.append(f"Uses {first['origin']}–{first['destination']}, not {q.origin}–{q.destination}")
    shifts = [s for s in option["date_shift_days"] if s]
    if shifts:
        out.append("Different dates: " + ", ".join(
            f"{'outbound' if i == 0 else 'return'} {s:+d} day{'s' if abs(s) != 1 else ''}"
            for i, s in enumerate(option["date_shift_days"]) if s
        ))
    return out


def _primary_currency(options: list[dict]) -> str | None:
    counts = Counter(o["currency"] for o in options if o["currency"])
    return counts.most_common(1)[0][0] if counts else None


def _rank(primary: str | None):
    """Sort key: offers in the search's main currency first, since amounts in
    different currencies are never compared; then totals that cover the bags
    asked for ahead of fares whose bag fees couldn't be priced (a $250 fare
    plus unknown bags isn't cheaper than a $310 total with them); then price;
    then time in the air."""
    def key(option: dict) -> tuple:
        priced = option["true_total_amount"] is not None
        amount = _money(option["true_total_amount"] if priced else option["total_amount"])
        return (
            option["currency"] != primary, not priced, amount,
            sum(sl["duration_minutes"] or 0 for sl in option["slices"]),
        )
    return key


def tool_view(option: dict) -> dict:
    """The compact form the model reads."""
    return {
        "offer_id": option["id"],
        "ticketing": option["ticketing"],
        "total": f"{option['currency']} {option['total_amount']}",
        "total_with_bags": (
            f"{option['currency']} {option['true_total_amount']}" if option["true_total_amount"] else None
        ),
        "bag_note": option["bag_note"],
        "carriers": option["carriers"],
        "slices": [
            {
                "route": f"{sl['origin']} {sl['departing_at'][11:16]} → {sl['destination']} {sl['arriving_at'][11:16]}",
                "date": sl["departing_at"][:10],
                "stops": sl["stops"],
                "duration_minutes": sl["duration_minutes"],
                "flights": [s["flight_number"] for s in sl["segments"]],
                "fare_brand": sl["fare_brand"],
            }
            for sl in option["slices"]
        ],
        "changeable": option["conditions"]["changeable"],
        "refundable": option["conditions"]["refundable"],
        "warnings": option["warnings"],
    }


# ── the per-run session ───────────────────────────────────────────────────────

class FlightSession:
    """One agent run's flight searches: the request budget, and every option
    it has shown the model, by id (the result can only use these)."""

    def __init__(self, access_token: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 today: date | None = None) -> None:
        self.test_data = access_token.startswith("duffel_test_")
        self._token = access_token
        self._transport = transport
        self._today = today
        self.options: dict[str, dict] = {}
        self.requests_used = 0
        self.searched_at: str | None = None
        self.query_summary: str | None = None

    def option(self, offer_id: str) -> dict | None:
        return self.options.get(offer_id)

    async def search(self, args: dict, *, seconds: float = SEARCH_SECONDS) -> dict:
        """Tool output: the cheapest options found, or `{error}`. Returns
        within about `seconds`, with whatever finished in time."""
        today = self._today or datetime.now(timezone.utc).date()
        try:
            q = parse_query(args, today=today)
        except FlightError as exc:
            return {"error": str(exc)}
        budget = min(MAX_REQUESTS_PER_SEARCH, MAX_OFFER_REQUESTS - self.requests_used)
        if budget <= 0:
            return {"error": "Flight search budget used up; finish with the offers you have."}
        client = DuffelClient(self._token, transport=self._transport)
        try:
            return await self._search(client, q, budget, today, deadline=time.monotonic() + seconds)
        finally:
            await client.aclose()

    async def _nearby(self, client: DuffelClient, code: str) -> list[str]:
        """Other airports within ~100 miles of `code`, an airport or a city.
        A city code (NYC) already searches every airport in the city, so those
        are left out: what comes back is the airports around it."""
        try:
            matches = await client.places(query=code)
            place = next(
                (p for p in matches if p.get("iata_code") == code and p.get("type") in ("airport", "city")), None,
            )
            if not place:
                return []
            own = {code} | {a.get("iata_code") for a in place.get("airports") or [] if a.get("iata_code")}
            anchor = next(
                (p for p in [place, *(place.get("airports") or [])]
                 if p.get("latitude") is not None and p.get("longitude") is not None),
                None,
            )
            if anchor is None:
                return []
            around = await client.places(lat=anchor["latitude"], lng=anchor["longitude"], rad=NEARBY_RADIUS_METRES)
        except (DuffelError, httpx.HTTPError):
            logger.info("nearby airport lookup failed for %s", code, exc_info=True)
            return []
        codes: list[str] = []
        for p in around:
            for airport in [p, *(p.get("airports") or [])] if p.get("type") == "city" else [p]:
                iata = airport.get("iata_code")
                if airport.get("type", "airport") == "airport" and iata and iata not in own and iata not in codes:
                    codes.append(iata)
        return codes[:MAX_NEARBY_AIRPORTS]

    async def _nearby_both(self, client: DuffelClient, q: FlightQuery, timeout: float) -> tuple[list[str], list[str]]:
        """Nearby airports for each end, never one that is (or is near) the
        other end: a short hop like SFO→SJC must not plan SJC→SJC."""
        try:
            near_o, near_d = await asyncio.wait_for(
                asyncio.gather(self._nearby(client, q.origin), self._nearby(client, q.destination)),
                timeout=max(0.0, timeout),
            )
        except TimeoutError:
            logger.info("nearby airport lookup ran out of time")
            return [], []
        shared = set(near_o) & set(near_d)
        return (
            [c for c in near_o if c != q.destination and c not in shared],
            [c for c in near_d if c != q.origin and c not in shared],
        )

    async def _offer_requests(
        self, client: DuffelClient, q: FlightQuery, variants: list[Variant], started: list[int], *, timeout: float,
    ) -> list[list[dict] | BaseException | None]:
        """Each variant's offers, its error, or None when time ran out first.
        `started[0]` counts the requests that actually went to Duffel."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        async def run(variant: Variant) -> list[dict]:
            async with semaphore:
                started[0] += 1
                return await client.offer_request(variant, q)

        tasks = [asyncio.create_task(run(v)) for v in variants]
        try:
            if tasks:
                await asyncio.wait(tasks, timeout=max(0.0, timeout))
        finally:
            for task in tasks:
                task.cancel()  # no-op on a finished task
            await asyncio.gather(*tasks, return_exceptions=True)
        return [
            None if task.cancelled() else (task.exception() or task.result())
            for task in tasks
        ]

    async def _search(self, client: DuffelClient, q: FlightQuery, budget: int, today: date, *,
                      deadline: float) -> dict:
        def left() -> float:
            return deadline - time.monotonic()

        origins, destinations = [q.origin], [q.destination]
        if q.nearby_airports:
            near_o, near_d = await self._nearby_both(client, q, min(NEARBY_SECONDS, left() - BAG_SECONDS))
            origins += near_o
            destinations += near_d
        variants, skipped = plan_variants(q, origins=origins, destinations=destinations, budget=budget, today=today)
        # Reserved up front, so an overlapping call can't overspend; what never
        # reached Duffel (time ran out first) is given back, even on cancel.
        self.requests_used += len(variants)
        started = [0]
        try:
            results = await self._offer_requests(client, q, variants, started, timeout=left() - BAG_SECONDS)
        finally:
            self.requests_used -= len(variants) - started[0]

        failed = timed_out = 0
        found: list[tuple[Variant, list[dict]]] = []
        for variant, result in zip(variants, results):
            if result is None:
                timed_out += 1
            elif isinstance(result, BaseException):
                failed += 1
                logger.info("duffel offer request failed: %s", result)
            else:
                found.append((variant, [o for o in (offer_option(raw, variant) for raw in result) if o]))
        if not found:
            if timed_out:
                return {"error": "The flight search ran out of time before the airline data provider answered. "
                                 "Try again with fewer dates or airports, or finish with what you have."}
            return {"error": "The flight search failed at the airline data provider. Try again or finish with what you have."}

        # Amounts are only compared within one currency: the exact trip's.
        exact = next((opts for v, opts in found if v is variants[0]), [])
        primary = _primary_currency(exact) or _primary_currency([o for _, opts in found for o in opts])
        key = _rank(primary)
        options: list[dict] = []
        legs: dict[str, list[dict]] = {"out": [], "back": []}
        for variant, parsed in found:
            parsed = sorted(parsed, key=key)[:MAX_OFFERS_KEPT_PER_REQUEST]
            (legs[variant.leg] if variant.leg else options).extend(parsed)
        legs["out"].sort(key=key)
        legs["back"].sort(key=key)
        for out in legs["out"][:MAX_LEGS_PAIRED]:
            for back in legs["back"][:MAX_LEGS_PAIRED]:
                pair = combine(out, back)
                if pair:
                    options.append(pair)

        # Same flights found by two requests: keep the cheaper.
        unique: dict[tuple, dict] = {}
        for option in sorted(options, key=key):
            unique.setdefault(_signature(option), option)
        ranked = sorted(unique.values(), key=key)

        await self._price_bags(client, q, ranked, timeout=left())
        for option in ranked:
            option["warnings"] = warnings_for(option, q)
        ranked.sort(key=key)

        for option in ranked[:MAX_OPTIONS_STORED]:
            self.options[option["id"]] = option
        self.searched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.query_summary = q.summary()
        shown = ranked[:MAX_TOOL_OPTIONS]
        out = {
            "searched": q.summary(),
            "offer_requests": started[0],
            "failed_requests": failed,
            "requests_left": MAX_OFFER_REQUESTS - self.requests_used,
            "currency": primary,
            "options": [tool_view(o) for o in shown],
            "note": "Choose by offer_id. Prices, times, bags and warnings on the page come from this data.",
        }
        notes = []
        if timed_out:
            out["timed_out_requests"] = timed_out
            notes.append(f"{timed_out} request(s) ran out of time and weren't counted against the budget.")
        if q.nearby_airports:
            out["nearby_airports"] = {"origin": origins[1:], "destination": destinations[1:]}
            if len(origins) + len(destinations) == 2:
                notes.append("No nearby airports were found, so only the airports asked for were searched.")
        if any(skipped.values()):
            out["not_searched"] = skipped
            notes.append(
                "Some other dates or airports weren't searched within this search's request budget. "
                "Search again with a narrower ask to try them."
            )
        others = sorted({o["currency"] for o in shown if o["currency"] != primary})
        if others:
            notes.append(
                f"Offers priced in {', '.join(others)} are listed after the {primary} offers: "
                "amounts in different currencies aren't comparable."
            )
        if any(o["true_total_amount"] is None for o in shown) and (q.checked_bags or q.carry_on_bags):
            notes.append(
                "Offers whose bag fees couldn't be priced are listed after the ones whose total includes "
                "the bags; their real cost is higher than the fare shown."
            )
        if notes:
            out["note"] += " " + " ".join(notes)
        return out

    async def _price_bags(self, client: DuffelClient, q: FlightQuery, ranked: list[dict], *,
                          timeout: float) -> None:
        """Fill `true_total_amount` for the cheapest options that lack the
        bags asked for: up to `MAX_OFFER_FETCHES` offer reads, concurrently,
        within `timeout`. An option that can't be priced says so."""
        if not q.checked_bags and not q.carry_on_bags:
            for option in ranked:
                option["true_total_amount"] = option["total_amount"]
            return
        needed: list[dict] = []
        for option in ranked:
            included = option["bags_included"]
            if included["checked"] >= q.checked_bags and included["carry_on"] >= q.carry_on_bags:
                option["true_total_amount"] = option["total_amount"]
                option["bag_note"] = "Bags you need are included"
            else:
                needed.append(option)
        # Cheapest first, whole options only: a separate-ticket pair needs
        # both of its offers read.
        wanted: list[str] = []
        for option in needed:
            new = [leg for leg in option["leg_ids"] if leg not in wanted]
            if len(wanted) + len(new) <= MAX_OFFER_FETCHES:
                wanted += new
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        async def extra_for(offer_id: str) -> Decimal | None:
            async with semaphore:
                offer = await client.offer(offer_id)
            included = _bags_included(offer)
            checked = bag_cost(offer, bag_type="checked", quantity=max(0, q.checked_bags - included["checked"]))
            carry = bag_cost(offer, bag_type="carry_on", quantity=max(0, q.carry_on_bags - included["carry_on"]))
            return None if checked is None or carry is None else checked + carry

        tasks = {offer_id: asyncio.create_task(extra_for(offer_id)) for offer_id in wanted}
        extras: dict[str, Decimal | None] = {}
        try:
            if tasks:
                await asyncio.wait(tasks.values(), timeout=max(0.0, timeout))
        finally:
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        for offer_id, task in tasks.items():
            if task.cancelled():
                continue
            if task.exception() is not None:
                logger.info("bag pricing failed for %s: %s", offer_id, task.exception())
                continue
            extras[offer_id] = task.result()

        for option in needed:
            parts = [extras.get(leg) for leg in option["leg_ids"]]
            if parts and all(part is not None for part in parts):
                option["true_total_amount"] = str(Decimal(option["total_amount"]) + sum(parts, Decimal(0)))
                option["bag_note"] = "Includes the airline's listed bag fees"
            else:
                option["bag_note"] = "Bag fees not priced; check with the airline"
