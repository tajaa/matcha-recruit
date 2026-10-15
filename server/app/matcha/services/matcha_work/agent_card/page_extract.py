"""Turn one fetched HTML page into the compact facts the agent can use.

Retail and review pages usually publish their product facts as schema.org
JSON-LD (`Product` with `offers` and `aggregateRating`) — far more reliable
than scraping visible text. The extractor prefers that, falls back to Open
Graph tags, and adds a bounded slice of visible text for everything else.
Output is DATA for the model, never instructions.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

MAX_TEXT_CHARS = 8_000
MAX_PRODUCTS = 3
MAX_REVIEWS = 5
MAX_JOBS = 2
# Homes, places, events and loose offers (Espresso Tasks reads these); each
# key appears only when the page has one, so other pages keep their shape.
MAX_LISTINGS = 4
MAX_PLACES = 3
MAX_EVENTS = 3
MAX_LOOSE_OFFERS = 4
LISTING_TYPES = frozenset({
    "Apartment", "SingleFamilyResidence", "House", "Residence", "Accommodation",
    "ApartmentComplex", "RealEstateListing", "Room", "Suite",
})
PLACE_TYPES = frozenset({
    "Place", "LocalBusiness", "Restaurant", "FoodEstablishment", "CafeOrCoffeeShop", "BarOrPub",
    "Bakery", "Store", "Hotel", "LodgingBusiness",
})
EVENT_TYPES = frozenset({"Event"})
OFFER_TYPES = frozenset({"Offer", "AggregateOffer"})
# In the general page view (the model's fetch_page output) a job description
# stays short; `job_postings` gives the job search the whole thing.
MAX_JOB_DESCRIPTION = 3_000
MAX_FULL_JOB_DESCRIPTION = 20_000


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _types(node: dict) -> set[str]:
    return {str(t) for t in _as_list(node.get("@type"))}


_MAX_LD_NODES = 2000
_MAX_LD_DEPTH = 40


def _walk_ld(node: Any):
    """Every dict in a JSON-LD blob, including @graph members and nesting.

    Iterative with a depth and node cap: JSON-LD is attacker-controlled, and a
    recursive walk over absurd nesting raises RecursionError.
    """
    stack: list[tuple[Any, int]] = [(node, 0)]
    seen = 0
    while stack and seen < _MAX_LD_NODES:
        current, depth = stack.pop()
        if depth > _MAX_LD_DEPTH:
            continue
        if isinstance(current, list):
            stack.extend((item, depth + 1) for item in reversed(current))
        elif isinstance(current, dict):
            seen += 1
            yield current
            for key in ("item", "itemListElement", "mainEntity", "@graph"):
                if key in current:
                    stack.append((current[key], depth + 1))


def _image_urls(value: Any, base: str) -> list[str]:
    urls = []
    for item in _as_list(value):
        if isinstance(item, dict):
            item = item.get("url") or item.get("contentUrl")
        if isinstance(item, str) and item.strip():
            urls.append(urljoin(base, item.strip()))
    return urls[:4]


def _offers(value: Any, base: str) -> list[dict]:
    out = []
    for offer in _as_list(value):
        if not isinstance(offer, dict):
            continue
        # AggregateOffer carries its own nested offers list.
        if "offers" in offer and "AggregateOffer" in _types(offer):
            out.extend(_offers(offer["offers"], base))
            if offer.get("lowPrice") is not None:
                out.append({
                    "price": offer.get("lowPrice"),
                    "currency": offer.get("priceCurrency"),
                    "availability": None,
                    "url": urljoin(base, offer["url"]) if isinstance(offer.get("url"), str) else None,
                    "seller": None,
                })
            continue
        seller = offer.get("seller")
        out.append({
            "price": offer.get("price") or offer.get("lowPrice"),
            "currency": offer.get("priceCurrency"),
            "availability": str(offer.get("availability") or "").rsplit("/", 1)[-1] or None,
            "url": urljoin(base, offer["url"]) if isinstance(offer.get("url"), str) else None,
            "seller": seller.get("name") if isinstance(seller, dict) else None,
        })
    return out[:6]


def _product(node: dict, base: str) -> dict:
    rating = node.get("aggregateRating") if isinstance(node.get("aggregateRating"), dict) else {}
    brand = node.get("brand")
    reviews = []
    for review in _as_list(node.get("review"))[:MAX_REVIEWS]:
        if not isinstance(review, dict):
            continue
        body = str(review.get("reviewBody") or review.get("description") or "").strip()
        if not body:
            continue
        rr = review.get("reviewRating") if isinstance(review.get("reviewRating"), dict) else {}
        author = review.get("author")
        reviews.append({
            "body": body[:400],
            "rating": rr.get("ratingValue"),
            "author": author.get("name") if isinstance(author, dict) else (author if isinstance(author, str) else None),
        })
    return {
        "name": str(node.get("name") or "").strip()[:200],
        "brand": brand.get("name") if isinstance(brand, dict) else (brand if isinstance(brand, str) else None),
        "description": str(node.get("description") or "").strip()[:600],
        "images": _image_urls(node.get("image"), base),
        "rating": {
            "value": rating.get("ratingValue"),
            "count": rating.get("reviewCount") or rating.get("ratingCount"),
            "best": rating.get("bestRating") or 5,
        } if rating.get("ratingValue") is not None else None,
        "offers": _offers(node.get("offers"), base),
        "reviews": reviews,
    }


def plain_text(value: Any, limit: int) -> str:
    """Text from a field that may hold HTML, one line per block, at most `limit`."""
    raw = str(value or "")
    if "<" in raw:
        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        raw = soup.get_text("\n", strip=True)
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    return "\n".join(line for line in lines if line)[:limit]


def _scalar(value: Any, limit: int = 24) -> str | int | float | None:
    """A number, or a short string; anything else (a nested object a page made
    up to smuggle text into the model's input) is dropped."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and value.strip():
        return value.strip()[:limit]
    return None


def _salary(raw: Any) -> dict | None:
    """schema.org `baseSalary`, reduced to the fields pay is read from."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {"currency": _scalar(raw.get("currency"), 8)}
    value = raw.get("value")
    if isinstance(value, dict):
        out["value"] = {key: _scalar(value.get(key)) for key in ("minValue", "maxValue", "value", "unitText")
                        if _scalar(value.get(key)) is not None}
    elif _scalar(value) is not None:
        out["value"] = _scalar(value)
        out["unitText"] = _scalar(raw.get("unitText"))
    else:
        return None
    return out


def _address(value: Any) -> str:
    parts = []
    for place in _as_list(value)[:3]:
        if not isinstance(place, dict):
            continue
        address = place.get("address") if isinstance(place.get("address"), dict) else place
        bits = [str(address.get(k) or "").strip() for k in
                ("addressLocality", "addressRegion", "addressCountry")]
        country = address.get("addressCountry")
        if isinstance(country, dict):
            bits[2] = str(country.get("name") or "").strip()
        text = ", ".join(b for b in bits if b)
        if text:
            parts.append(text)
    return "; ".join(parts)[:200]


def _job_posting(node: dict, base: str, description_limit: int = MAX_JOB_DESCRIPTION) -> dict:
    """schema.org JobPosting: the facts a job search needs, pay included."""
    org = node.get("hiringOrganization")
    salary = _salary(node.get("baseSalary"))
    location_type = " ".join(str(t) for t in _as_list(node.get("jobLocationType")))
    url = node.get("url")
    return {
        "title": str(node.get("title") or "").strip()[:200],
        "company": (org.get("name") if isinstance(org, dict) else org if isinstance(org, str) else "") or "",
        "location": _address(node.get("jobLocation")),
        "remote": "TELECOMMUTE" in location_type.upper(),
        "base_salary": salary,
        "date_posted": str(node.get("datePosted") or "")[:40] or None,
        "valid_through": str(node.get("validThrough") or "")[:40] or None,
        "employment_type": " ".join(str(t) for t in _as_list(node.get("employmentType")))[:80] or None,
        "url": urljoin(base, url) if isinstance(url, str) else None,
        "description": plain_text(node.get("description"), description_limit),
    }


def _text_of(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit] if isinstance(value, (str, int, float)) else ""


def _quantity(value: Any) -> dict | None:
    """schema.org QuantitativeValue (or a bare number): `{value, unit}`."""
    if isinstance(value, dict):
        number = _scalar(value.get("value"))
        if number is None:
            return None
        return {"value": number, "unit": _scalar(value.get("unitCode") or value.get("unitText"), 16)}
    number = _scalar(value)
    return {"value": number, "unit": None} if number is not None else None


def _rating(node: dict) -> dict | None:
    rating = node.get("aggregateRating") if isinstance(node.get("aggregateRating"), dict) else {}
    if _scalar(rating.get("ratingValue")) is None:
        return None
    return {
        "value": _scalar(rating.get("ratingValue")),
        "count": _scalar(rating.get("reviewCount") or rating.get("ratingCount")),
        "best": _scalar(rating.get("bestRating")) or 5,
    }


def _price_unit(offer: dict) -> Any:
    spec = offer.get("priceSpecification")
    for item in _as_list(spec):
        if isinstance(item, dict):
            unit = _scalar(item.get("unitText") or item.get("unitCode") or item.get("billingDuration"), 16)
            if unit is not None:
                return unit
    return _scalar(offer.get("unitText"), 16)


def _loose_offer(node: dict, base: str) -> dict:
    """An Offer on its own (a rental's rent, a ticket): price, currency, and
    the unit it is charged per when the page says (MONTH, NIGHT)."""
    price = node.get("price") if node.get("price") is not None else node.get("lowPrice")
    spec = node.get("priceSpecification")
    if price is None:
        for item in _as_list(spec):
            if isinstance(item, dict) and item.get("price") is not None:
                price = item.get("price")
                break
    item = node.get("itemOffered") if isinstance(node.get("itemOffered"), dict) else {}
    url = node.get("url")
    return {
        "price": _scalar(price),
        "currency": _scalar(node.get("priceCurrency"), 8),
        "unit": _price_unit(node),
        "availability": str(node.get("availability") or "").rsplit("/", 1)[-1][:40] or None,
        "available_from": _scalar(node.get("availabilityStarts") or node.get("validFrom"), 40),
        "item": _text_of(item.get("name"), 200) or None,
        "url": urljoin(base, url) if isinstance(url, str) else None,
    }


def _pets(value: Any) -> str | None:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return _text_of(value, 120) or None


def _amenities(value: Any) -> list[str]:
    out = []
    for item in _as_list(value)[:20]:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(item, dict) and item.get("value") is False:
            continue
        text = _text_of(name, 60)
        if text:
            out.append(text)
    return out[:12]


def _listing(node: dict, base: str) -> dict:
    """A home for rent or sale (Apartment, House, RealEstateListing...)."""
    about = node.get("about") if isinstance(node.get("about"), dict) else {}
    entity = node.get("mainEntity") if isinstance(node.get("mainEntity"), dict) else {}
    home = {**about, **entity, **{k: v for k, v in node.items() if v not in (None, "", [])}}
    url = home.get("url")
    offers = [_loose_offer(o, base) for o in _as_list(home.get("offers")) if isinstance(o, dict)]
    return {
        "type": sorted(_types(node) & LISTING_TYPES)[0] if _types(node) & LISTING_TYPES else "Residence",
        "name": _text_of(home.get("name"), 200),
        "url": urljoin(base, url) if isinstance(url, str) else None,
        "description": plain_text(home.get("description"), 600),
        "address": _address(home),
        "bedrooms": _scalar(home.get("numberOfBedrooms") or home.get("numberOfRooms")),
        "bathrooms": _scalar(home.get("numberOfBathroomsTotal") or home.get("numberOfFullBathrooms")),
        "floor_size": _quantity(home.get("floorSize")),
        "pets_allowed": _pets(home.get("petsAllowed")),
        "amenities": _amenities(home.get("amenityFeature")),
        "date_posted": _scalar(home.get("datePosted"), 40),
        "images": _image_urls(home.get("image") or home.get("photo"), base),
        "offers": offers[:4],
        **_geo(home.get("geo")),
    }


def _geo(value: Any) -> dict:
    """`{"geo": {"lat", "lng"}}` from a schema.org GeoCoordinates, or {} (so a
    page without one keeps its exact shape)."""
    value = value[0] if isinstance(value, list) and value else value
    if not isinstance(value, dict):
        return {}
    try:
        lat, lng = float(value.get("latitude")), float(value.get("longitude"))
    except (TypeError, ValueError):
        return {}
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return {}
    return {"geo": {"lat": lat, "lng": lng}}


def _hours(node: dict) -> list[str]:
    out = [_text_of(h, 80) for h in _as_list(node.get("openingHours")) if _text_of(h, 80)]
    for spec in _as_list(node.get("openingHoursSpecification"))[:14]:
        if not isinstance(spec, dict):
            continue
        days = " ".join(str(d).rsplit("/", 1)[-1] for d in _as_list(spec.get("dayOfWeek")))[:60]
        opens, closes = _text_of(spec.get("opens"), 8), _text_of(spec.get("closes"), 8)
        if days and opens and closes:
            out.append(f"{days} {opens}-{closes}")
    return out[:14]


def _place(node: dict, base: str) -> dict:
    """A restaurant, shop or other place: where it is, when it is open, how it rates."""
    url = node.get("url")
    menu = node.get("hasMenu") or node.get("menu")
    if isinstance(menu, dict):
        menu = menu.get("url")
    cuisine = ", ".join(_text_of(c, 40) for c in _as_list(node.get("servesCuisine")) if _text_of(c, 40))
    return {
        "type": sorted(_types(node) & PLACE_TYPES)[0],
        "name": _text_of(node.get("name"), 200),
        "url": urljoin(base, url) if isinstance(url, str) else None,
        "address": _address(node),
        "telephone": _text_of(node.get("telephone"), 40) or None,
        "price_range": _text_of(node.get("priceRange"), 20) or None,
        "cuisine": cuisine[:120] or None,
        "rating": _rating(node),
        "hours": _hours(node),
        "accepts_reservations": _pets(node.get("acceptsReservations")),
        "menu_url": urljoin(base, menu) if isinstance(menu, str) else None,
        "images": _image_urls(node.get("image") or node.get("photo"), base),
        **_geo(node.get("geo")),
    }


def _event(node: dict, base: str) -> dict:
    url = node.get("url")
    location = node.get("location")
    venue = location.get("name") if isinstance(location, dict) else location
    return {
        "name": _text_of(node.get("name"), 200),
        "url": urljoin(base, url) if isinstance(url, str) else None,
        "start": _scalar(node.get("startDate"), 40),
        "end": _scalar(node.get("endDate"), 40),
        "venue": _text_of(venue, 120) or None,
        "address": _address(location) if isinstance(location, dict) else "",
        "offers": [_loose_offer(o, base) for o in _as_list(node.get("offers")) if isinstance(o, dict)][:3],
    }


def _ld_nodes(soup: BeautifulSoup):
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            blob = json.loads(raw)
        except (ValueError, TypeError, RecursionError):
            continue
        yield from _walk_ld(blob)


def job_postings(html: bytes, final_url: str) -> list[dict]:
    """Every schema.org JobPosting on the page (up to MAX_JOBS), full description."""
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for node in _ld_nodes(soup):
        if "JobPosting" in _types(node):
            jobs.append(_job_posting(node, final_url, MAX_FULL_JOB_DESCRIPTION))
            if len(jobs) >= MAX_JOBS:
                break
    return jobs


def extract_page(html: bytes, final_url: str) -> dict:
    """Compact, bounded page facts for the model."""
    soup = BeautifulSoup(html, "lxml")
    products: list[dict] = []
    jobs: list[dict] = []
    more: dict[str, list[dict]] = {"listings": [], "places": [], "events": [], "offers": []}
    # Nodes a listing or event already read (its offers, the home a listing
    # is `about`), so the walk does not report them twice.
    consumed: set[int] = set()
    for node in _ld_nodes(soup):
        types = _types(node)
        if id(node) in consumed:
            continue
        if "Product" in types and len(products) < MAX_PRODUCTS:
            products.append(_product(node, final_url))
        elif "JobPosting" in types and len(jobs) < MAX_JOBS:
            jobs.append(_job_posting(node, final_url))
        elif types & LISTING_TYPES and len(more["listings"]) < MAX_LISTINGS:
            more["listings"].append(_listing(node, final_url))
            consumed.update(id(n) for key in ("offers", "about", "mainEntity") for n in _as_list(node.get(key)))
        elif types & PLACE_TYPES and len(more["places"]) < MAX_PLACES:
            more["places"].append(_place(node, final_url))
        elif types & EVENT_TYPES and len(more["events"]) < MAX_EVENTS:
            more["events"].append(_event(node, final_url))
            consumed.update(id(o) for o in _as_list(node.get("offers")))
        elif types & OFFER_TYPES and len(more["offers"]) < MAX_LOOSE_OFFERS and not products:
            more["offers"].append(_loose_offer(node, final_url))

    def meta(*names: str) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return None

    og_image = meta("og:image", "og:image:url", "twitter:image")
    title = meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"]):
        tag.decompose()
    text = " ".join((soup.body or soup).get_text(" ", strip=True).split())

    page = {
        "url": final_url,
        "title": (title or "")[:200],
        "description": (meta("og:description", "description") or "")[:500],
        "og_image": urljoin(final_url, og_image) if og_image else None,
        "products": products,
        "text": text[:MAX_TEXT_CHARS],
        "text_truncated": len(text) > MAX_TEXT_CHARS,
    }
    # Only when the page has one, so product pages keep their exact shape.
    if jobs:
        page["jobs"] = jobs
    for key, found in more.items():
        if found:
            page[key] = found
    return page


def page_urls(page: dict) -> set[str]:
    """URLs a fetched page vouches for: itself plus its JSON-LD offer URLs."""
    urls = {page["url"]} if page.get("url") else set()
    for product in page.get("products") or []:
        for offer in product.get("offers") or []:
            if offer.get("url"):
                urls.add(offer["url"])
    for key in ("listings", "places", "events", "offers"):
        for item in page.get(key) or []:
            for url in (item.get("url"), *(o.get("url") for o in item.get("offers") or [])):
                if isinstance(url, str) and url:
                    urls.add(url)
    return urls


MAX_LINKS = 30


def _site(host: str | None) -> str:
    host = (host or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def page_links(html: bytes, base: str, limit: int = MAX_LINKS) -> list[dict]:
    """Links on the page to other pages of the same site, with their text:
    how a listing or results page points at each item's own page. Navigation,
    headers and footers are skipped, as are short and anchor-only links.
    Only Espresso Tasks asks for these; `extract_page` is unchanged."""
    soup = BeautifulSoup(html, "lxml")
    site = _site(urlsplit(base).hostname)
    out: list[dict] = []
    seen = {base.split("#")[0]}
    for anchor in soup.find_all("a", href=True):
        if anchor.find_parent(["nav", "header", "footer"]):
            continue
        href = urljoin(base, str(anchor["href"]).strip()).split("#")[0]
        parts = urlsplit(href)
        if parts.scheme not in ("http", "https") or _site(parts.hostname) != site:
            continue
        if len(parts.path.rstrip("/")) < 8 or href in seen:
            continue
        text = " ".join(anchor.get_text(" ", strip=True).split())[:120]
        if len(text) < 6:
            continue
        seen.add(href)
        out.append({"text": text, "url": href})
        if len(out) >= limit:
            break
    return out
