"""What a finding can say about itself, and how each fact is read and checked. Pure.

A finding's `fields` map a library key to one entry:

    {"value": 3200.0, "currency": "USD", "unit": "month", "display": "$3,200/mo",
     "status": "verified", "evidence": {"quote": "...", "url": "...", "origin": "jsonld"}}

`status` is the whole point:

  verified  read by code from structured data (a provider's API, the page's
            schema.org JSON-LD), or from the item's own page text, or a model's
            claim whose quote is printed on the item's own page
  claimed   a model's claim whose quote is printed on some other page it loaded
            (a review, a roundup): shown with its source, never used to rule an
            item out or in
  unknown   nothing usable; the entry is not stored at all

Hard constraints (`ranking.py`) only ever act on verified entries, so a page
that says nothing, or says it somewhere else, makes an item "Unconfirmed",
never a violation and never a match.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from ..playbook import ItemField

# ── the library ──────────────────────────────────────────────────────────────

PETS = {"dogs": "Dogs OK", "cats": "Cats OK", "pets_ok": "Pets OK", "none": "No pets"}
AMENITIES = {
    "laundry": "Laundry", "parking": "Parking", "dishwasher": "Dishwasher",
    "air_conditioning": "Air conditioning", "gym": "Gym", "doorman": "Doorman",
    "elevator": "Elevator", "outdoor_space": "Outdoor space", "furnished": "Furnished",
}


def _f(key: str, label: str, type_: str, **kw) -> ItemField:
    return ItemField(key=key, label=label, type=type_, **kw)


LIBRARY: dict[str, ItemField] = {f.key: f for f in (
    _f("price", "Price", "money", higher_is_better=False),
    _f("rating", "Rating", "rating", higher_is_better=True),
    _f("review_count", "Reviews", "number", higher_is_better=True),
    _f("beds", "Beds", "number", higher_is_better=True),
    _f("baths", "Baths", "number", higher_is_better=True),
    _f("sqft", "Sq ft", "number", higher_is_better=True),
    _f("pets", "Pets", "tags", tags=PETS),
    _f("amenities", "Amenities", "tags", tags=AMENITIES),
    _f("available_date", "Available", "date", higher_is_better=False),
    _f("neighborhood", "Neighborhood", "text"),
    _f("address", "Address", "text"),
    _f("brand", "Brand", "text"),
    _f("seller", "Seller", "text"),
    _f("in_stock", "In stock", "bool", higher_is_better=True),
    _f("shipping", "Shipping", "text"),
    _f("cuisine", "Cuisine", "text"),
    _f("price_level", "Price level", "text"),
    _f("hours", "Hours", "text"),
    _f("phone", "Phone", "text"),
    _f("when", "When", "text"),
    _f("venue", "Venue", "text"),
)}

STATUS_RANK = {"verified": 2, "claimed": 1}
# Among entries of the same status, structured data beats text, text beats a model.
ORIGIN_RANK = {"provider": 3, "jsonld": 3, "page_text": 2, "browser": 2, "model": 1}

_TAG_WORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "pets": {
        "dogs": ("dog", "dogs", "canine"),
        "cats": ("cat", "cats", "feline"),
        "pets_ok": ("pet friendly", "pet-friendly", "pets allowed", "pets ok", "pets welcome", "yes"),
        "none": ("no pets", "pets not allowed", "no animals", "no dogs", "dogs not allowed", "none", "no"),
    },
    "amenities": {
        "laundry": ("laundry", "washer", "w/d", "washer/dryer"),
        "parking": ("parking", "garage"),
        "dishwasher": ("dishwasher",),
        "air_conditioning": ("air conditioning", "a/c", "central air"),
        "gym": ("gym", "fitness"),
        "doorman": ("doorman", "concierge"),
        "elevator": ("elevator",),
        "outdoor_space": ("balcony", "patio", "yard", "deck", "outdoor space", "roof deck"),
        "furnished": ("furnished",),
    },
}
_CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "CA$", "AUD": "A$"}
_UNIT_SUFFIX = {"month": "/mo", "night": "/night", "week": "/wk", "year": "/yr", "day": "/day"}
_UNITS = (
    ("month", ("month", "mon", "mo", "p1m", "monthly")),
    ("night", ("night", "nightly")),
    ("week", ("week", "wk", "p1w", "weekly")),
    ("year", ("year", "ann", "yr", "p1y", "annual", "annually")),
    ("day", ("day", "dai", "p1d", "daily")),
)
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_AMOUNT = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?\s?([kK])?\b")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: Any, limit: int = 200) -> str:
    return " ".join(_CONTROL.sub(" ", str(value or "")).split())[:limit]


def _norm(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


# ── values ───────────────────────────────────────────────────────────────────

def unit_of(raw: Any) -> str | None:
    """A billing period from a schema.org unit or loose text ("MONTH", "/mo")."""
    text = _norm(str(raw or ""))
    if not text:
        return None
    for unit, words in _UNITS:
        if text.strip("/ ") in words or any(
            re.search(rf"(?:/\s*|\bper\s+|\ba\s+|\b){re.escape(w)}\b", text) for w in words if len(w) > 1
        ):
            return unit
    return None


def amounts(text: str) -> list[float]:
    out = []
    for match in _AMOUNT.finditer(text or ""):
        value = float(match.group(1).replace(",", "") + (match.group(2) or ""))
        out.append(value * 1000 if match.group(3) else value)
    return out


def _number(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        found = amounts(str(raw or ""))
        if not found:
            return None
        value = found[0]
    return value if value == value and 0 <= value < 1e9 else None


def _currency(raw: Any, hint: str = "") -> str | None:
    code = str(raw or "").strip().upper()
    if re.fullmatch(r"[A-Z]{3}", code):
        return code
    for code, symbol in (("EUR", "€"), ("GBP", "£"), ("USD", "$")):
        if symbol in hint:
            return code
    return None


def _date(raw: Any, today: date) -> date | None:
    if isinstance(raw, date):
        return raw
    text = _norm(str(raw or "")).strip(" .,")
    if not text:
        return None
    if text in ("now", "immediately", "today", "available now"):
        return today
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        pass
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", text)
    if match:
        month, day, year = int(match.group(1)), int(match.group(2)), match.group(3)
    else:
        match = re.fullmatch(r"([a-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", text)
        if not match or match.group(1) not in _MONTHS:
            return None
        month, day, year = _MONTHS[match.group(1)], int(match.group(2)), match.group(3)
    try:
        if year:
            y = int(year)
            return date(y + 2000 if y < 100 else y, month, day)
        guess = date(today.year, month, day)
        # No year: the next time that date comes round.
        return guess if guess >= today else date(today.year + 1, month, day)
    except ValueError:
        return None


def _says(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) is not None


def tags_in(field_key: str, raw: Any) -> list[str]:
    """The tag values `raw` names ("Dogs welcome" -> ["dogs"])."""
    words = _TAG_WORDS.get(field_key) or {}
    values = raw if isinstance(raw, (list, tuple)) else [raw]
    out: list[str] = []
    for item in values:
        text = _norm(str(item or ""))
        if not text:
            continue
        for tag, synonyms in words.items():
            hit = text == tag or text in synonyms or any(len(s) >= 3 and _says(text, s) for s in synonyms)
            if hit and tag not in out:
                out.append(tag)
    # "No pets" wins over everything else said in the same breath.
    if field_key == "pets" and "none" in out:
        return ["none"]
    return out


def coerce(spec: ItemField, raw: Any, *, today: date) -> Any:
    """The value as its field stores it, or None when `raw` is not one."""
    if raw is None:
        return None
    if spec.type in ("money", "number"):
        return _number(raw)
    if spec.type == "rating":
        value = _number(raw)
        return value if value is not None and value <= 5 else None
    if spec.type == "bool":
        if isinstance(raw, bool):
            return raw
        text = _norm(str(raw))
        if text in ("yes", "true", "in stock", "instock", "available"):
            return True
        if text in ("no", "false", "out of stock", "outofstock", "sold out", "soldout", "unavailable"):
            return False
        return None
    if spec.type == "tags":
        return tags_in(spec.key, raw) or None
    if spec.type == "date":
        found = _date(raw, today)
        return found.isoformat() if found else None
    return clean_text(raw) or None


def display(spec: ItemField, value: Any, *, currency: str | None = None, unit: str | None = None) -> str:
    if spec.type == "money":
        symbol = _CURRENCY_SYMBOL.get(currency or "USD", f"{currency} ")
        amount = f"{value:,.0f}" if float(value).is_integer() or value >= 100 else f"{value:,.2f}"
        return f"{symbol}{amount}{_UNIT_SUFFIX.get(unit or '', '')}"
    if spec.type == "number":
        return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"
    if spec.type == "rating":
        return f"{value:.1f}"
    if spec.type == "bool":
        return "Yes" if value else "No"
    if spec.type == "tags":
        return ", ".join(spec.tags.get(tag, tag) for tag in value)
    if spec.type == "date":
        day = date.fromisoformat(value)
        return f"{day:%b} {day.day}, {day.year}"
    return str(value)


def entry(spec: ItemField, raw: Any, *, status: str, origin: str, today: date,
          url: str | None = None, quote: str | None = None,
          currency: str | None = None, unit: str | None = None) -> dict | None:
    """One stored field, or None when `raw` is not a value of this field."""
    value = coerce(spec, raw, today=today)
    if value is None or status not in STATUS_RANK:
        return None
    out: dict[str, Any] = {"value": value, "status": status}
    if spec.type == "money":
        out["currency"] = _currency(currency, str(raw)) or "USD"
        out["unit"] = unit_of(unit) if unit else unit_of(str(raw) if isinstance(raw, str) else "")
    out["display"] = display(spec, value, currency=out.get("currency"), unit=out.get("unit"))
    out["evidence"] = {"quote": clean_text(quote, 300) if quote else None, "url": url, "origin": origin}
    return out


def better(new: dict, old: dict | None) -> bool:
    if old is None:
        return True
    new_rank = (STATUS_RANK.get(new.get("status"), 0), ORIGIN_RANK.get((new.get("evidence") or {}).get("origin"), 0))
    old_rank = (STATUS_RANK.get(old.get("status"), 0), ORIGIN_RANK.get((old.get("evidence") or {}).get("origin"), 0))
    return new_rank > old_rank


def merge(fields: dict, new: dict) -> dict:
    """`fields` with each entry of `new` that is better than what is there."""
    out = dict(fields or {})
    for key, value in (new or {}).items():
        if key in LIBRARY and isinstance(value, dict) and better(value, out.get(key)):
            out[key] = value
    return out


# ── checking a model's claim ─────────────────────────────────────────────────

def verify_quote(quote: str, source: str) -> bool:
    q = _norm(quote)
    return len(q) >= 8 and q in _norm(source)


def supports(spec: ItemField, value: Any, quote: str) -> bool:
    """Whether the quote states this value, not just something nearby."""
    text = _norm(quote)
    if spec.type in ("money", "number", "rating"):
        return any(abs(a - float(value)) <= max(0.5, abs(float(value)) * 0.005) for a in amounts(quote))
    if spec.type == "tags":
        words = _TAG_WORDS.get(spec.key) or {}
        return all(any(s in text for s in (*words.get(tag, ()), tag.replace("_", " "))) for tag in value)
    if spec.type == "date":
        day = date.fromisoformat(value)
        return str(day.day) in re.findall(r"\d+", text) or any(w in text for w in ("now", "immediately"))
    if spec.type == "bool":
        return True
    words = [w for w in re.findall(r"[a-z0-9]+", _norm(str(value))) if len(w) > 1]
    return bool(words) and sum(w in text for w in words) >= max(1, round(len(words) * 0.6))


# ── reading a page (`agent_card.page_extract.extract_page` output) ───────────

def _overlap(a: str, b: str) -> float:
    wa, wb = set(re.findall(r"[a-z0-9]+", _norm(a))), set(re.findall(r"[a-z0-9]+", _norm(b)))
    return len(wa & wb) / max(1, min(len(wa), len(wb))) if wa and wb else 0.0


def _the_one(nodes: list[dict], title: str) -> dict | None:
    """The page's one node about this item: the only one, or the one whose
    name matches the title. A results page about many is no item's evidence."""
    if len(nodes) == 1:
        return nodes[0]
    named = [n for n in nodes if _overlap(str(n.get("name") or ""), title) >= 0.6]
    return named[0] if len(named) == 1 else None


def _set(out: dict, key: str, raw: Any, *, url: str, quote: str, today: date, origin: str = "jsonld",
         **money) -> None:
    made = entry(LIBRARY[key], raw, status="verified", origin=origin, today=today, url=url, quote=quote, **money)
    if made is not None:
        out[key] = made


def from_page(page: dict, *, url: str, title: str, today: date) -> dict:
    """Fields read from a page's schema.org data: verified, origin `jsonld`."""
    out: dict[str, dict] = {}
    product = _the_one(page.get("products") or [], title)
    if product:
        offers = [o for o in product.get("offers") or [] if _number(o.get("price")) is not None]
        if offers:
            cheapest = min(offers, key=lambda o: _number(o.get("price")))
            _set(out, "price", cheapest.get("price"), url=url, today=today,
                 quote=f"schema.org Offer price {cheapest.get('price')} {cheapest.get('currency') or ''}".strip(),
                 currency=cheapest.get("currency"))
            stock = str(cheapest.get("availability") or "")
            if stock:
                _set(out, "in_stock", "in stock" if stock.lower() in ("instock", "limitedavailability", "onlineonly")
                     else "out of stock" if stock.lower() in ("outofstock", "soldout", "discontinued") else None,
                     url=url, today=today, quote=f"schema.org availability {stock}")
            if cheapest.get("seller"):
                _set(out, "seller", cheapest["seller"], url=url, today=today, quote=f"seller {cheapest['seller']}")
        _rating(out, product.get("rating"), url=url, today=today)
        if product.get("brand"):
            _set(out, "brand", product["brand"], url=url, today=today, quote=f"brand {product['brand']}")
    listing = _the_one(page.get("listings") or [], title)
    if listing:
        offer = next((o for o in listing.get("offers") or [] if _number(o.get("price")) is not None), None)
        if offer:
            _set(out, "price", offer["price"], url=url, today=today,
                 quote=f"schema.org Offer price {offer['price']} {offer.get('currency') or ''} {offer.get('unit') or ''}".strip(),
                 currency=offer.get("currency"), unit=offer.get("unit"))
            if offer.get("available_from"):
                _set(out, "available_date", offer["available_from"], url=url, today=today,
                     quote=f"available from {offer['available_from']}")
        for key, field_key in (("bedrooms", "beds"), ("bathrooms", "baths")):
            if listing.get(key) is not None:
                _set(out, field_key, listing[key], url=url, today=today, quote=f"schema.org {key} {listing[key]}")
        size = listing.get("floor_size") or {}
        if _number(size.get("value")) is not None:
            sqft = _number(size["value"])
            if str(size.get("unit") or "").upper() in ("MTK", "M2", "SQM"):
                sqft = round(sqft * 10.764)
            _set(out, "sqft", sqft, url=url, today=today, quote=f"schema.org floorSize {size['value']} {size.get('unit') or ''}".strip())
        if listing.get("pets_allowed"):
            pets = "pets allowed" if listing["pets_allowed"] == "yes" else "no pets" if listing["pets_allowed"] == "no" else listing["pets_allowed"]
            _set(out, "pets", pets, url=url, today=today, quote=f"schema.org petsAllowed {listing['pets_allowed']}")
        if listing.get("amenities"):
            _set(out, "amenities", listing["amenities"], url=url, today=today,
                 quote="schema.org amenityFeature " + ", ".join(listing["amenities"]))
        if listing.get("address"):
            _set(out, "address", listing["address"], url=url, today=today, quote=f"address {listing['address']}")
    place = _the_one(page.get("places") or [], title)
    if place:
        _rating(out, place.get("rating"), url=url, today=today)
        for key, field_key in (("address", "address"), ("cuisine", "cuisine"), ("price_range", "price_level"),
                               ("telephone", "phone")):
            if place.get(key):
                _set(out, field_key, place[key], url=url, today=today, quote=f"schema.org {key} {place[key]}")
        if place.get("hours"):
            hours = "; ".join(place["hours"])
            _set(out, "hours", hours, url=url, today=today, quote=f"schema.org openingHours {hours}")
    event = _the_one(page.get("events") or [], title)
    if event:
        if event.get("start"):
            _set(out, "when", event["start"], url=url, today=today, quote=f"schema.org startDate {event['start']}")
        if event.get("venue"):
            _set(out, "venue", event["venue"], url=url, today=today, quote=f"schema.org location {event['venue']}")
        offer = next((o for o in event.get("offers") or [] if _number(o.get("price")) is not None), None)
        if offer and "price" not in out:
            _set(out, "price", offer["price"], url=url, today=today,
                 quote=f"schema.org Offer price {offer['price']} {offer.get('currency') or ''}".strip(),
                 currency=offer.get("currency"))
    if "price" not in out and not page.get("products") and not page.get("listings"):
        offer = _the_one([o for o in page.get("offers") or [] if _number(o.get("price")) is not None], title)
        if offer:
            _set(out, "price", offer["price"], url=url, today=today,
                 quote=f"schema.org Offer price {offer['price']} {offer.get('currency') or ''} {offer.get('unit') or ''}".strip(),
                 currency=offer.get("currency"), unit=offer.get("unit"))
    return out


def _rating(out: dict, rating: Any, *, url: str, today: date) -> None:
    if not isinstance(rating, dict) or _number(rating.get("value")) is None:
        return
    value, best = _number(rating["value"]), _number(rating.get("best")) or 5.0
    if best and best != 5:
        value = round(value * 5 / best, 2)
    _set(out, "rating", value, url=url, today=today, quote=f"schema.org ratingValue {rating['value']}")
    if _number(rating.get("count")) is not None:
        _set(out, "review_count", rating["count"], url=url, today=today,
             quote=f"schema.org reviewCount {rating['count']}")


# ── scanning a home listing's own text (conservative) ────────────────────────

_RENT = re.compile(r"\$\s?(\d{1,2},?\d{3})(?:\.\d{2})?\s*(?:/\s*|per\s+|a\s+)(?:mo\b|mon\b|month\b)", re.I)
_BEDS = re.compile(r"\b(\d)\s*(?:bd|bds|bed|beds|bedrooms?|br)\b|\b(studio)\b", re.I)
_BATHS = re.compile(r"\b(\d(?:\.5)?)\s*(?:ba|bath|baths|bathrooms?)\b", re.I)
_SQFT = re.compile(r"\b(\d{1,2},?\d{3}|\d{3})\s*(?:sq\.?\s*ft\.?|sqft|square\s+feet|ft²)", re.I)
_DOGS = re.compile(r"\bdogs?\s+(?:are\s+)?(?:ok|okay|allowed|welcome|friendly)\b|\bdog[- ]friendly\b", re.I)
_CATS = re.compile(r"\bcats?\s+(?:are\s+)?(?:ok|okay|allowed|welcome)\b|\bcat[- ]friendly\b", re.I)
_NO_PETS = re.compile(r"\bno\s+pets\b|\bpets\s+(?:are\s+)?not\s+allowed\b|\bno\s+(?:dogs|animals)\b", re.I)
_AVAILABLE = re.compile(
    r"\bavailable\s+(?:on\s+|from\s+)?(now|immediately|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|"
    r"\d{1,2}/\d{1,2}(?:/\d{2,4})?)", re.I)
QUOTE_SIDE = 80


def _window(text: str, match: re.Match) -> str:
    """The match with up to QUOTE_SIDE characters either side, whole words
    only, so the quote stays a verbatim slice of the (whitespace-collapsed) text."""
    start = max(0, match.start() - QUOTE_SIDE)
    if start > 0:
        space = text.find(" ", start, match.start())
        start = space + 1 if space != -1 else match.start()
    end = min(len(text), match.end() + QUOTE_SIDE)
    if end < len(text):
        space = text.rfind(" ", match.end(), end)
        end = space if space != -1 else match.end()
    return text[start:end].strip()


def _single(matches: list[tuple[Any, re.Match]]) -> tuple[Any, re.Match] | None:
    """The one value the text states; None when it states several (a building
    page listing many units is no unit's evidence)."""
    values = {value for value, _ in matches}
    return matches[0] if len(values) == 1 else None


def scan_listing_text(text: str, *, url: str, today: date) -> dict:
    """Fields a home listing's own page states in words: verified, origin
    `page_text`, each with the sentence it came from."""
    text = " ".join(str(text or "").split())
    out: dict[str, dict] = {}

    def put(key: str, found: list[tuple[Any, re.Match]], **money) -> None:
        one = _single(found)
        if one is not None:
            _set(out, key, one[0], url=url, today=today, quote=_window(text, one[1]), origin="page_text", **money)

    put("price", [(float(m.group(1).replace(",", "")), m) for m in _RENT.finditer(text)], unit="month")
    put("beds", [(0.0 if m.group(2) else float(m.group(1)), m) for m in _BEDS.finditer(text)])
    put("baths", [(float(m.group(1)), m) for m in _BATHS.finditer(text)])
    put("sqft", [(float(m.group(1).replace(",", "")), m) for m in _SQFT.finditer(text)])
    no_pets = list(_NO_PETS.finditer(text))
    if no_pets:
        _set(out, "pets", "no pets", url=url, today=today, quote=_window(text, no_pets[0]), origin="page_text")
    else:
        dogs, cats = _DOGS.search(text), _CATS.search(text)
        allowed = [name for name, match in (("dogs", dogs), ("cats", cats)) if match]
        if allowed:
            first = dogs or cats
            quote = _window(text, first)
            if dogs and cats and _norm(_window(text, cats)) not in _norm(quote):
                allowed = ["dogs"]  # say only what the quote shows
            _set(out, "pets", allowed, url=url, today=today, quote=quote, origin="page_text")
    put("available_date", [(_date(m.group(1), today), m) for m in _AVAILABLE.finditer(text)
                           if _date(m.group(1), today) is not None])
    return out


def check_text(fields: dict) -> str:
    """Everything a finding's fields say, as one string a summary's numbers
    are checked against."""
    parts = []
    for value in (fields or {}).values():
        if isinstance(value, dict):
            parts.append(str(value.get("display") or ""))
            parts.append(str(value.get("value") or ""))
    return " ".join(parts)
