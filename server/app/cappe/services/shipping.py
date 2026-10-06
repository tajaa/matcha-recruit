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

The store's currency (`cappe_sites.currency`) is a short list of two-decimal
currencies: every amount here is stored in hundredths, and a zero-decimal
currency (JPY) would have charged 100x the price shown.
"""
from __future__ import annotations

from dataclasses import dataclass
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
class Destination:
    """The rates for one ship-to country."""

    country: str
    flat_cents: int
    free_threshold_cents: Optional[int]
    charge_tax: bool
    zone_id: Optional[str] = None  # None = the home country

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


def resolve_destination(site: Any, zones: Iterable[dict], country: Optional[str]) -> Optional[Destination]:
    """The rates for shipping to `country` (default: home), or None when the
    store doesn't ship there. The home country always wins over a zone that
    also lists it; a named country wins over "the rest of the world"."""
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
