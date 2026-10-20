"""Where a store ships, what it costs to get there, and what it charges in.

A store has a HOME country. Its existing shipping settings on `cappe_sites`
(flat rate, free-shipping threshold) and its tax rate are the home rates —
for years they were simply "the" rates, with Stripe told to take US addresses
only. Shipping zones (`cappe_shipping_zones`, the `shipping_zones` plan
feature) add other destinations, each with its own flat rate, threshold and a
"charge tax here" switch; one zone may cover the rest of the world.

The buyer picks a ship-to country in the bag. `/quote` prices that country and
order creation stores it on the order (`ship_country`), and the Stripe payment
page then accepts an address in that country only — so the address can never
land somewhere the price wasn't for. No zones = the home country only, which is
exactly the old behaviour (with the home country now settable).

A destination may also have its own delivery OPTIONS (`cappe_shipping_rates`,
the same plan feature): shipped, picked up, or delivered locally, each priced
by what is in the bag (count, weight, value) — the buyer picks one in the bag.
A destination with none keeps its one flat rate, which `shipping_options`
presents as a single option, so nothing changes for a store that never sets
them up.

The store's currency (`cappe_sites.currency`) is a short list of two-decimal
currencies: every amount here is stored in hundredths, and a zero-decimal
currency (JPY) would have charged 100x the price shown.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status

DEFAULT_HOME_COUNTRY = "US"
DEFAULT_CURRENCY = "USD"

# Keep in sync with the migration (`zzzzcappe43`).
SITE_CURRENCIES = (
    "USD", "CAD", "EUR", "GBP", "AUD", "NZD", "CHF", "SEK", "NOK", "DKK",
    "PLN", "MXN", "SGD", "HKD",
)

MAX_ZONES = 20
MAX_RATES = 10            # delivery options per destination
METHODS = ("ship", "pickup", "local_delivery")
FLAT_RATE_ID = "flat"     # the option a destination without rate rows offers

# Every country Stripe Checkout accepts a shipping address in
# (`shipping_address_collection.allowed_countries`, stripe-python 16), less its
# "ZZ" placeholder. Validating against Stripe's own list means a zone can never
# name a country that would make the payment page fail to open.
SHIP_COUNTRIES = frozenset("""
AC AD AE AF AG AI AL AM AO AQ AR AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ
BL BM BN BO BQ BR BS BT BV BW BY BZ CA CD CF CG CH CI CK CL CM CN CO CR CV
CW CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FO FR GA GB GD GE
GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HN HR HT HU ID IE IL IM IN
IO IQ IS IT JE JM JO JP KE KG KH KI KM KN KR KW KY KZ LA LB LC LI LK LR LS
LT LU LV LY MA MC MD ME MF MG MK ML MM MN MO MQ MR MS MT MU MV MW MX MY MZ
NA NC NE NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PY
QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX
SZ TA TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG US UY UZ VA VC
VE VG VN VU WF WS XK YE YT ZA ZM ZW
""".split())

_ZONE_COLS = (
    "id, name, countries, rest_of_world, flat_cents, free_threshold_cents, "
    "charge_tax, sort_order"
)


def _get(row: Any, key: str) -> Any:
    try:
        return row.get(key) if row is not None else None
    except AttributeError:
        return None


def home_country(site: Any) -> str:
    """The store's home country (US for a store that never set one)."""
    return (_get(site, "home_country") or DEFAULT_HOME_COUNTRY).upper()


def site_currency(site: Any) -> str:
    """The store's currency (USD for a store that never set one)."""
    return (_get(site, "currency") or DEFAULT_CURRENCY).upper()


@dataclass(frozen=True)
class ShipRate:
    """One delivery option for a destination (`cappe_shipping_rates`)."""

    id: Optional[str]                 # None = the destination's own flat rate
    name: str
    method: str = "ship"
    amount_cents: int = 0
    per_item_cents: int = 0           # each item after the first
    min_subtotal_cents: Optional[int] = None
    max_subtotal_cents: Optional[int] = None
    min_weight_g: Optional[int] = None
    max_weight_g: Optional[int] = None
    free_over_cents: Optional[int] = None
    delivery_min_days: Optional[int] = None
    delivery_max_days: Optional[int] = None
    postal_codes: tuple = ()
    instructions: Optional[str] = None


@dataclass(frozen=True)
class ShipLoad:
    """What the bag asks a carrier to move: the physical units that don't ship
    free, their weight and their per-unit surcharges, and where (for local
    delivery). The goods' value is passed beside it, after any promo code."""

    units: int = 0
    weight_g: int = 0
    surcharge_cents: int = 0
    postal_code: Optional[str] = None


def ship_load(parts: Iterable[tuple[Any, int]], postal_code: Optional[str] = None) -> ShipLoad:
    """`parts` are (product row, quantity) for the bag's physical lines."""
    units = weight = surcharge = 0
    for product, qty in parts:
        if product is None or _get(product, "ships_free"):
            continue
        units += qty
        weight += int(_get(product, "weight_g") or 0) * qty
        surcharge += int(_get(product, "shipping_surcharge_cents") or 0) * qty
    return ShipLoad(units=units, weight_g=weight, surcharge_cents=surcharge, postal_code=postal_code)


@dataclass(frozen=True)
class Destination:
    """The rates for one ship-to country."""

    country: str
    flat_cents: int
    free_threshold_cents: Optional[int]
    charge_tax: bool
    zone_id: Optional[str] = None  # None = the home country
    rates: tuple = ()              # ShipRate options; () = the flat rate only

    @property
    def is_home(self) -> bool:
        return self.zone_id is None


def home_destination(site: Any) -> Destination:
    """The home rates, from the site's own shipping settings. Tax applies."""
    return Destination(
        country=home_country(site),
        flat_cents=int(_get(site, "shipping_flat_cents") or 0),
        free_threshold_cents=_get(site, "shipping_free_threshold_cents"),
        charge_tax=True,
    )


def _zone_destination(country: str, zone: dict) -> Destination:
    return Destination(
        country=country,
        flat_cents=int(zone.get("flat_cents") or 0),
        free_threshold_cents=zone.get("free_threshold_cents"),
        charge_tax=bool(zone.get("charge_tax")),
        zone_id=str(zone["id"]),
    )


def resolve_destination(site: Any, zones: Iterable[dict], country: Optional[str],
                        rates: Optional[dict] = None) -> Optional[Destination]:
    """The rates for shipping to `country` (default: home), or None when the
    store doesn't ship there. The home country always wins over a zone that
    also lists it; a named country wins over "the rest of the world".
    `rates` ({zone id or None: [ShipRate]}, `load_rates`) adds the
    destination's delivery options."""
    dest = _resolve(site, zones, country)
    if dest is None or not rates:
        return dest
    return replace(dest, rates=tuple(rates.get(dest.zone_id) or ()))


def _resolve(site: Any, zones: Iterable[dict], country: Optional[str]) -> Optional[Destination]:
    home = home_country(site)
    code = (country or home).upper()
    if code == home:
        return home_destination(site)
    zones = list(zones)
    for zone in zones:
        if not zone.get("rest_of_world") and code in (zone.get("countries") or ()):
            return _zone_destination(code, zone)
    if code in SHIP_COUNTRIES:
        for zone in zones:
            if zone.get("rest_of_world"):
                return _zone_destination(code, zone)
    return None


# ── delivery options ─────────────────────────────────────────────────────────

def _postal(value: Optional[str]) -> str:
    return "".join((value or "").split()).upper()


def postal_matches(rate: ShipRate, postal_code: Optional[str]) -> bool:
    """A local delivery area is a list of postal-code prefixes ("941", "SW1");
    an empty list covers the whole destination. Either way it needs the
    buyer's postal code: a local delivery is never offered before the bag
    knows where it goes, so a client that sends no address (an app whose
    card page collects it) is never defaulted onto one it can't complete."""
    code = _postal(postal_code)
    if not code:
        return False
    return not rate.postal_codes or any(code.startswith(_postal(p)) for p in rate.postal_codes if _postal(p))


def rate_price(rate: ShipRate, load: ShipLoad, goods_cents: int) -> Optional[int]:
    """What `rate` costs for this bag, or None when it isn't offered for it
    (outside its value or weight band, or outside its delivery area).

    Free when nothing in the bag counts (every item ships free), when the
    goods cost nothing (a giveaway, which no payment would ever settle — what
    the flat rate always did), or over the rate's free-over amount. Otherwise
    its amount, plus its per-item amount for each item after the first, plus
    the products' own surcharges (not for pickup: nothing is carried)."""
    def outside(value, low, high):
        return (low is not None and value < low) or (high is not None and value > high)

    if outside(goods_cents, rate.min_subtotal_cents, rate.max_subtotal_cents):
        return None
    if outside(load.weight_g, rate.min_weight_g, rate.max_weight_g):
        return None
    if rate.method == "local_delivery" and not postal_matches(rate, load.postal_code):
        return None
    if load.units <= 0 or goods_cents <= 0:
        return 0
    if rate.free_over_cents is not None and goods_cents >= rate.free_over_cents:
        return 0
    if rate.method == "pickup":
        return rate.amount_cents
    return rate.amount_cents + rate.per_item_cents * (load.units - 1) + load.surcharge_cents


def _days(handling: Optional[int], transit: Optional[int]) -> Optional[int]:
    if handling is None and transit is None:
        return None
    return (handling or 0) + (transit or 0)


def handling_days(site: Any) -> tuple[Optional[int], Optional[int]]:
    """Business days to get an order out of the door (the store's own setting)."""
    days = [d for d in (_get(site, "handling_days_min"), _get(site, "handling_days_max")) if d is not None]
    return (min(days), max(days)) if days else (None, None)


def shipping_options(dest: Destination, load: ShipLoad, goods_cents: int, *, label: str = "Shipping",
                     handling: tuple = (None, None)) -> list[dict]:
    """The options the buyer can pick for this bag, in the owner's order — the
    first is the default. A destination without rate rows offers its flat rate
    as the one option. Estimates are handling time plus time in transit."""
    rates = dest.rates or (ShipRate(id=None, name=label or "Shipping", amount_cents=dest.flat_cents,
                                    free_over_cents=dest.free_threshold_cents),)
    out = []
    for rate in rates:
        cents = rate_price(rate, load, goods_cents)
        if cents is None:
            continue
        out.append({
            "id": rate.id or FLAT_RATE_ID, "label": rate.name, "method": rate.method, "amount_cents": cents,
            "delivery_min_days": _days(handling[0], rate.delivery_min_days),
            "delivery_max_days": _days(handling[1], rate.delivery_max_days),
            "instructions": rate.instructions if rate.method == "pickup" else None,
        })
    return out


def choose_option(options: list[dict], rate_id: Optional[str], *, strict: bool) -> Optional[dict]:
    """The option asked for, else the default. `strict` (placing an order)
    refuses an option the bag showed but the order no longer gets — a price
    changed under the buyer — instead of quietly charging another."""
    if rate_id:
        hit = next((o for o in options if o["id"] == str(rate_id)), None)
        if hit is not None:
            return hit
        if strict:
            raise HTTPException(
                status_code=409,
                detail="That delivery option isn't available for this order any more. Check your bag and try again.",
            )
    return options[0] if options else None


def no_delivery_option() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail="None of this store's delivery options fits this order. Contact the store to arrange it.",
    )


_RATE_COLS = (
    "id, zone_id, name, method, amount_cents, per_item_cents, min_subtotal_cents, max_subtotal_cents, "
    "min_weight_g, max_weight_g, free_over_cents, delivery_min_days, delivery_max_days, postal_codes, "
    "instructions, sort_order"
)


def _rate(row: Any) -> ShipRate:
    return ShipRate(
        id=str(row["id"]), name=row["name"], method=row["method"], amount_cents=int(row["amount_cents"] or 0),
        per_item_cents=int(row["per_item_cents"] or 0), min_subtotal_cents=row["min_subtotal_cents"],
        max_subtotal_cents=row["max_subtotal_cents"], min_weight_g=row["min_weight_g"],
        max_weight_g=row["max_weight_g"], free_over_cents=row["free_over_cents"],
        delivery_min_days=row["delivery_min_days"], delivery_max_days=row["delivery_max_days"],
        postal_codes=tuple(row["postal_codes"] or ()), instructions=row["instructions"],
    )


async def _fetch_rate_rows(conn, site_id):
    return await conn.fetch(
        f"SELECT {_RATE_COLS} FROM cappe_shipping_rates WHERE site_id = $1 ORDER BY sort_order, created_at",
        site_id,
    )


async def load_rates(conn, site_id, ent) -> dict:
    """{zone id (str) or None for home: [ShipRate]} — empty without the plan
    feature, so a downgraded store is back to one flat rate (its rates kept)."""
    if ent is not None and not ent.has("shipping_zones"):
        return {}
    rows = await _fetch_rate_rows(conn, site_id)
    out: dict = {}
    for r in rows:
        out.setdefault(str(r["zone_id"]) if r["zone_id"] else None, []).append(_rate(r))
    return out


async def load_rate_rows(conn, site_id) -> list[dict]:
    """Every saved rate as a row, for the settings page."""
    rows = await _fetch_rate_rows(conn, site_id)
    return [{**dict(r), "postal_codes": list(r["postal_codes"] or [])} for r in rows]


def validate_rates(rates: list[Any], *, where: str) -> None:
    """Refuse a destination's options that can't be priced or picked."""
    if len(rates) > MAX_RATES:
        raise HTTPException(422, f"{where}: at most {MAX_RATES} delivery options")
    for r in rates:
        for low, high, what in ((r.min_subtotal_cents, r.max_subtotal_cents, "order value"),
                                (r.min_weight_g, r.max_weight_g, "weight"),
                                (r.delivery_min_days, r.delivery_max_days, "delivery time")):
            if low is not None and high is not None and low > high:
                raise HTTPException(422, f"“{r.name}”: the lowest {what} is above the highest.")


def ship_countries(site: Any, zones: Iterable[dict]) -> list[str]:
    """Every country the buyer can pick, home first, then alphabetical."""
    home = home_country(site)
    zones = list(zones)
    if any(z.get("rest_of_world") for z in zones):
        others = set(SHIP_COUNTRIES)
    else:
        others = {c for z in zones for c in (z.get("countries") or ())}
    others.discard(home)
    return [home, *sorted(others)]


def not_shippable(country: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=f"This store doesn't ship to {country.upper()}. Choose another country.",
    )


async def load_zones(conn, site_id, ent) -> list[dict]:
    """The store's zones — none at all when its plan doesn't include them, so
    a downgraded store ships home only (its zones are kept, not deleted)."""
    if ent is not None and not ent.has("shipping_zones"):
        return []
    rows = await conn.fetch(
        f"SELECT {_ZONE_COLS} FROM cappe_shipping_zones WHERE site_id = $1 ORDER BY sort_order, created_at",
        site_id,
    )
    return [dict(r) for r in rows]


def validate_zones(zones: list[Any], *, home: str) -> None:
    """Refuse a zone set that can't price unambiguously. `zones` are the
    request models (`countries` already upper-cased and checked by the model)."""
    if len(zones) > MAX_ZONES:
        raise HTTPException(422, f"At most {MAX_ZONES} shipping zones")
    seen: dict[str, str] = {}
    rest = 0
    for zone in zones:
        if zone.rest_of_world:
            rest += 1
        elif not zone.countries:
            raise HTTPException(
                422,
                f"“{zone.name}” needs at least one country, or turn on “everywhere else”.",
            )
        for code in zone.countries:
            if code == home:
                raise HTTPException(
                    422,
                    f"{code} is your home country — its rates are your main shipping settings, not a zone.",
                )
            if code in seen:
                raise HTTPException(
                    422,
                    f"{code} is in both “{seen[code]}” and “{zone.name}”. Each country can be in one zone.",
                )
            seen[code] = zone.name
    if rest > 1:
        raise HTTPException(422, "Only one zone can cover everywhere else")
