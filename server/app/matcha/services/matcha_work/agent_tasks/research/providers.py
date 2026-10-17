"""Structured listings for research tasks: Google Maps and Google Shopping.

For products, places and apartment buildings, a provider gives what a web
search can't: a price, a rating, a point on the map and a link as data rather
than prose a model read. Those come in as findings whose fields are verified
with origin `provider`, the way Google Jobs is for job search. Anything else
(events) has no provider and is found by the model with web search.

Google Maps comes straight from Google (`GooglePlaces`: the Places API (New)
Text Search with `GOOGLE_MAPS_API_KEY`, the Google Maps Platform key Tell-Us's
place search uses), else from a search API as Shopping does. Google has no
public API for Shopping results, so those come through SearchAPI
(`SEARCH_API_KEY`) when set, else SerpApi (`SERP_API_KEY`), the same keys job
search uses: both serve Google's results as JSON with nearly the same fields.
`choose_provider(source)` puts the ones with keys in order (`Listings`): one
that refuses for good or is down is passed over for the next, by
`search_apis`' rules, which job search follows too. Only the query text (and,
for an area, its map box) leaves the server. Every call counts against the
round's provider budget (`chain.grant`).

A Shopping result links to Google's own product page, not a store's: neither
provider gives the store's link in the results. A second call per product
(`stores`: SearchAPI `google_product_offers`, SerpApi
`google_immersive_product`) lists the stores selling it, each with its own
link and price; `with_store` keeps the listing's seller there, so the finding
links to a page that is its own (and can be read for availability).
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Callable
from urllib.parse import parse_qsl, quote_plus, urlsplit

import httpx

from app.matcha.services.matcha_work import search_apis
from app.matcha.services.matcha_work.agent_card.schema import normalize_url
from app.matcha.services.matcha_work.search_apis import ProviderError, SleepFn

from . import fields as F
from .geo import point_of

logger = logging.getLogger(__name__)

MAX_RESULTS = 20
MAX_STORES = 13
KINDS = {"shopping": "product", "places": "place"}


@dataclass
class ProviderItem:
    kind: str
    title: str
    url: str | None
    subtitle: str = ""
    provider: str = ""
    provider_id: str | None = None
    fields: dict = field(default_factory=dict)
    image_url: str | None = None
    # Shopping: what `stores` takes to list the stores selling it.
    offers_token: str | None = None
    # Google Maps: where it is, (lat, lng).
    point: tuple[float, float] | None = None


@dataclass(frozen=True)
class Store:
    """One store selling a Shopping product: its name, its own page, its price."""

    name: str
    link: str
    price_text: str = ""
    price: float | None = None


def _http(url: Any) -> str | None:
    return url.strip() if isinstance(url, str) and normalize_url(url) else None


# Ad-click and tracking hosts: following one of these registers a paid click.
AD_HOSTS = ("googleadservices.com", "doubleclick.net", "googlesyndication.com", "google-analytics.com")


def is_google(url: str | None) -> bool:
    """A page of Google's (Shopping, Maps, search, its ad clicks), never a
    store's or place's own."""
    normalized = normalize_url(url)
    if not normalized:
        return False
    host = normalized.split("/")[2]
    return "google" in host.split(".") or any(host == h or host.endswith("." + h) for h in AD_HOSTS)


def store_link(raw: Any) -> str | None:
    """A store's own page: Google's redirect (`/url?q=`) unwrapped, Google itself refused."""
    link = _http(raw)
    if link and is_google(link) and urlsplit(link).path == "/url":
        params = dict(parse_qsl(urlsplit(link).query))
        link = _http(params.get("q") or params.get("url"))
    return link if link and not is_google(link) else None


def _name_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _token(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= 4096 else None


def with_store(item: ProviderItem, stores: list[Store], *, today: date) -> ProviderItem:
    """The finding at a store's own page: the listing's seller when it is among
    the stores (its facts stand), else the first store, whose price and name
    replace the listing's (its delivery note was the other seller's)."""
    if not stores:
        return item
    seller = _name_key(item.subtitle)
    match = next((s for s in stores if seller and _name_key(s.name) == seller), None)
    if match is not None:
        return replace(item, url=match.link)
    store = stores[0]
    # The offers carry no currency of their own: the listing's is the market's.
    currency = (item.fields.get("price") or {}).get("currency")
    out = {k: v for k, v in item.fields.items() if k not in ("price", "seller", "shipping")}
    if store.price is not None:
        _put(out, "price", store.price, url=store.link, today=today, currency=currency,
             quote=f"Google Shopping: {store.price_text or store.price} at {store.name}")
    _put(out, "seller", store.name, url=store.link, today=today, quote=f"Google Shopping seller {store.name}")
    return replace(item, url=store.link, subtitle=store.name, fields=out)


def _put(out: dict, key: str, raw: Any, *, quote: str, url: str | None, today: date, **money) -> None:
    made = F.entry(F.LIBRARY[key], raw, status="verified", origin="provider", today=today,
                   url=url, quote=quote, **money)
    if made is not None:
        out[key] = made


def shopping_item(raw: dict, *, today: date) -> ProviderItem | None:
    title = F.clean_text(raw.get("title"), 200)
    url = _http(raw.get("link")) or _http(raw.get("product_link"))
    if not title or not url:
        return None
    seller = F.clean_text(raw.get("source") or raw.get("seller"), 80)
    out: dict = {}
    price = raw.get("extracted_price") if isinstance(raw.get("extracted_price"), (int, float)) else raw.get("price")
    if price is not None:
        _put(out, "price", price, url=url, today=today,
             quote=f"Google Shopping: {F.clean_text(raw.get('price') or price, 40)}"
                   f"{' at ' + seller if seller else ''}",
             currency=raw.get("currency"))
    if raw.get("rating") is not None:
        _put(out, "rating", raw.get("rating"), url=url, today=today, quote=f"Google Shopping rating {raw.get('rating')}")
    if raw.get("reviews") is not None:
        _put(out, "review_count", raw.get("reviews"), url=url, today=today,
             quote=f"Google Shopping reviews {raw.get('reviews')}")
    if seller:
        _put(out, "seller", seller, url=url, today=today, quote=f"Google Shopping seller {seller}")
    delivery = F.clean_text(raw.get("delivery") or raw.get("shipping"), 80)
    if delivery:
        _put(out, "shipping", delivery, url=url, today=today, quote=f"Google Shopping: {delivery}")
    return ProviderItem(
        kind="product", title=title, url=url, subtitle=seller, provider="google_shopping",
        provider_id=F.clean_text(raw.get("product_id"), 80) or None, fields=out,
        image_url=_http(raw.get("thumbnail")),
        offers_token=_token(raw.get("product_token") or raw.get("immersive_product_page_token")),
    )


def _store(name: Any, link: Any, price_text: Any, price: Any) -> Store | None:
    name = F.clean_text(name, 80)
    link = store_link(link)
    if not name or not link:
        return None
    number = price if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0 else None
    return Store(name=name, link=link, price_text=F.clean_text(price_text, 40), price=number)


def place_item(raw: dict, *, today: date) -> ProviderItem | None:
    title = F.clean_text(raw.get("title"), 200)
    if not title:
        return None
    place_id = F.clean_text(raw.get("place_id"), 200) or None
    website = _http(raw.get("website"))
    maps = (f"https://www.google.com/maps/search/?api=1&query={quote_plus(title)}"
            f"&query_place_id={quote_plus(place_id)}") if place_id else None
    url = website or maps
    if not url:
        return None
    out: dict = {}
    address = F.clean_text(raw.get("address"), 200)
    for key, value in (("rating", raw.get("rating")), ("review_count", raw.get("reviews")),
                       ("address", address), ("price_level", raw.get("price")),
                       ("phone", raw.get("phone")), ("cuisine", raw.get("type"))):
        if value not in (None, ""):
            _put(out, key, value, url=url, today=today, quote=f"Google Maps {key.replace('_', ' ')}: {F.clean_text(value, 120)}")
    hours = raw.get("open_hours") or raw.get("operating_hours") or raw.get("hours") or raw.get("open_state")
    if isinstance(hours, dict):
        hours = "; ".join(f"{day}: {F.clean_text(text, 40)}" for day, text in list(hours.items())[:7])
    if isinstance(hours, str) and hours.strip():
        _put(out, "hours", hours, url=url, today=today, quote=f"Google Maps hours: {F.clean_text(hours, 200)}")
    return ProviderItem(
        kind="place", title=title, url=url, subtitle=address, provider="google_maps",
        provider_id=place_id, fields=out, image_url=_http(raw.get("thumbnail")),
        point=point_of(raw.get("gps_coordinates")),
    )


class _Api:
    name = ""
    base_url = ""

    def __init__(self, key: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 sleep: SleepFn = asyncio.sleep, today: Callable[[], date] = date.today):
        self._key = key
        self._transport = transport
        self._sleep = sleep
        self._today = today

    def _params(self, engine: str, query: str, page: int) -> dict:  # pragma: no cover - abstract
        raise NotImplementedError

    @staticmethod
    def _near(params: dict, ll: str | None) -> dict:
        """A map search centred on `ll` (`@lat,lng,zoom`), the way both APIs take it."""
        return {**params, "ll": ll} if ll and params.get("engine") == "google_maps" else params

    async def _get(self, params: dict) -> dict:
        data = await search_apis.answer(
            self.name, lambda client: client.get(self.base_url, params={**params, "api_key": self._key}),
            transport=self._transport, sleep=self._sleep, sku=params.get("engine"),
        )
        error = search_apis.result_error(data)
        if error:
            raise ProviderError(f"{self.name}: {error[:200]}")
        return data

    async def search(self, source: str, query: str, *, page: int = 1, ll: str | None = None) -> list[ProviderItem]:
        """One page of `shopping` or `places` results for the query text; a
        places search centred on `ll` when given."""
        today = self._today()
        if source == "shopping":
            data = await self._get(self._params("google_shopping", query, page))
            rows, build = data.get("shopping_results"), shopping_item
        elif source == "places":
            data = await self._get(self._near(self._params("google_maps", query, page), ll))
            rows, build = data.get("local_results"), place_item
        else:
            raise ValueError(f"unknown source {source!r}")
        items = []
        for raw in (rows if isinstance(rows, list) else [])[:MAX_RESULTS]:
            if isinstance(raw, dict):
                made = build(raw, today=today)
                if made is not None:
                    items.append(made)
        return items

    async def locate(self, query: str) -> tuple[str, tuple[float, float]] | None:
        """One place on the map, `(its name, (lat, lng))`: the place Google Maps
        answers with, else its first result."""
        data = await self._get(self._params("google_maps", query, 1))
        locals_ = data.get("local_results") if isinstance(data.get("local_results"), list) else []
        for row in (data.get("place_result"), data.get("place_results"), *locals_[:1]):
            if isinstance(row, dict) and point_of(row.get("gps_coordinates")):
                return F.clean_text(row.get("title"), 120) or query, point_of(row["gps_coordinates"])
        return None

    def _stores_params(self, token: str) -> dict:  # pragma: no cover - abstract
        raise NotImplementedError

    def _stores(self, data: dict) -> list[Store]:  # pragma: no cover - abstract
        raise NotImplementedError

    async def stores(self, token: str) -> list[Store]:
        """The stores selling one Shopping product (its `offers_token`), each at its own page."""
        return self._stores(await self._get(self._stores_params(token)))[:MAX_STORES]


class SearchApi(_Api):
    name = "SearchAPI"
    base_url = "https://www.searchapi.io/api/v1/search"

    def _params(self, engine: str, query: str, page: int) -> dict:
        return {"engine": engine, "q": query, "page": page}

    def _stores_params(self, token: str) -> dict:
        return {"engine": "google_product_offers", "product_token": token}

    def _stores(self, data: dict) -> list[Store]:
        rows = data.get("offers")
        out = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict):
                merchant = row.get("merchant") if isinstance(row.get("merchant"), dict) else {}
                made = _store(merchant.get("name") or row.get("seller"), row.get("link"),
                              row.get("price"), row.get("extracted_price"))
                if made is not None:
                    out.append(made)
        return out


class SerpApi(_Api):
    name = "SerpApi"
    base_url = "https://serpapi.com/search.json"

    def _params(self, engine: str, query: str, page: int) -> dict:
        params = {"engine": engine, "q": query}
        if engine == "google_maps":
            params["type"] = "search"
        if page > 1:
            params["start"] = (page - 1) * MAX_RESULTS  # SerpApi pages by result offset
        return params

    def _stores_params(self, token: str) -> dict:
        return {"engine": "google_immersive_product", "page_token": token}

    def _stores(self, data: dict) -> list[Store]:
        product = data.get("product_results") if isinstance(data.get("product_results"), dict) else {}
        rows = product.get("stores")
        out = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict):
                made = _store(row.get("name"), row.get("link"), row.get("price"), row.get("extracted_price"))
                if made is not None:
                    out.append(made)
        return out


# ── Google Maps from Google ──────────────────────────────────────────────────

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
# Website, phone, rating and hours make each search Google's "Enterprise" Text
# Search SKU; the building's own site is what the task reads next, so it stays.
SEARCH_MASK = ",".join([*(f"places.{f}" for f in (
    "id", "displayName", "formattedAddress", "location", "websiteUri", "nationalPhoneNumber", "rating",
    "userRatingCount", "priceLevel", "primaryTypeDisplayName", "regularOpeningHours.weekdayDescriptions",
    "businessStatus")), "nextPageToken"])
LOCATE_MASK = "places.displayName,places.location"
# Text Search answers at most three pages of 20.
MAX_PAGES = 3
PRICE_LEVELS = {"PRICE_LEVEL_FREE": "Free", "PRICE_LEVEL_INEXPENSIVE": "$", "PRICE_LEVEL_MODERATE": "$$",
                "PRICE_LEVEL_EXPENSIVE": "$$$", "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$"}
_LL = re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),(\d+(?:\.\d+)?)z")
MILES_PER_DEGREE = 69.0


def map_box(ll: str | None) -> dict | None:
    """The area a map centred on `ll` (`@lat,lng,zoom`) shows, as a Places
    rectangle: 5 miles each way at 13z, twice that for each zoom level out."""
    match = _LL.fullmatch(ll or "")
    if not match:
        return None
    lat, lng, zoom = float(match[1]), float(match[2]), float(match[3])
    half = 5.0 * 2 ** (13 - zoom)
    dlat = half / MILES_PER_DEGREE
    dlng = half / (MILES_PER_DEGREE * max(0.05, math.cos(math.radians(lat))))
    return {"low": {"latitude": max(-90.0, lat - dlat), "longitude": max(-180.0, lng - dlng)},
            "high": {"latitude": min(90.0, lat + dlat), "longitude": min(180.0, lng + dlng)}}


def _text(raw: Any) -> Any:
    """A Places `LocalizedText`'s text."""
    return raw.get("text") if isinstance(raw, dict) else None


def google_place_item(raw: dict, *, today: date) -> ProviderItem | None:
    """A Places API place, made the way `place_item` makes a search API's
    Google Maps result. A place Google marks closed for good is skipped."""
    if raw.get("businessStatus") == "CLOSED_PERMANENTLY":
        return None
    hours = raw.get("regularOpeningHours") if isinstance(raw.get("regularOpeningHours"), dict) else {}
    days = [d for d in hours.get("weekdayDescriptions") or [] if isinstance(d, str)]
    return place_item({
        "title": _text(raw.get("displayName")), "place_id": raw.get("id"), "website": raw.get("websiteUri"),
        "address": raw.get("formattedAddress"), "rating": raw.get("rating"), "reviews": raw.get("userRatingCount"),
        "price": PRICE_LEVELS.get(raw.get("priceLevel")), "phone": raw.get("nationalPhoneNumber"),
        "type": _text(raw.get("primaryTypeDisplayName")), "hours": "; ".join(days[:7]) or None,
        "gps_coordinates": raw.get("location"),
    }, today=today)


class GooglePlaces:
    """Google Maps places from Google's own Places API (New) Text Search. Places
    only: there is no Shopping here."""

    name = "Google Places"

    def __init__(self, key: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 sleep: SleepFn = asyncio.sleep, today: Callable[[], date] = date.today):
        self._key = key
        self._transport = transport
        self._sleep = sleep
        self._today = today

    async def _post(self, body: dict, mask: str) -> dict:
        headers = {"X-Goog-Api-Key": self._key, "X-Goog-FieldMask": mask}
        # The mask sets the SKU Google bills (ai_usage.API_PRICING).
        sku = "text_search_pro" if mask == LOCATE_MASK else "text_search_enterprise"
        return await search_apis.answer(self.name, lambda client: client.post(PLACES_URL, json=body, headers=headers),
                                        transport=self._transport, sleep=self._sleep, sku=sku)

    async def search(self, source: str, query: str, *, page: int = 1, ll: str | None = None) -> list[ProviderItem]:
        """One page of places for the query text, kept inside the map area
        `ll` shows when given. Google pages by token, so page n takes n calls."""
        if source != "places":
            raise ValueError(f"{self.name} has no {source!r} search")
        if page > MAX_PAGES:
            return []
        body: dict = {"textQuery": query, "pageSize": MAX_RESULTS, "languageCode": "en"}
        box = map_box(ll)
        if box:
            body["locationRestriction"] = {"rectangle": box}
        data: dict = {}
        token = None
        for n in range(page):
            if n and not token:
                return []
            data = await self._post({**body, "pageToken": token} if token else body, SEARCH_MASK)
            token = data.get("nextPageToken")
        today = self._today()
        rows = data.get("places")
        items = []
        for raw in (rows if isinstance(rows, list) else [])[:MAX_RESULTS]:
            if isinstance(raw, dict):
                made = google_place_item(raw, today=today)
                if made is not None:
                    items.append(made)
        return items

    async def locate(self, query: str) -> tuple[str, tuple[float, float]] | None:
        """One place on the map, `(its name, (lat, lng))`: Google's first answer."""
        data = await self._post({"textQuery": query, "pageSize": 1, "languageCode": "en"}, LOCATE_MASK)
        rows = data.get("places") if isinstance(data.get("places"), list) else []
        for row in rows[:1]:
            if isinstance(row, dict) and point_of(row.get("location")):
                return F.clean_text(_text(row.get("displayName")), 120) or query, point_of(row["location"])
        return None


class Listings(search_apis.Fallback):
    """The APIs for a source, in order (`search_apis.Fallback`). A Shopping
    product's `offers_token` is marked with the API that gave it."""

    label = "research listings"

    async def search(self, source: str, query: str, *, page: int = 1, ll: str | None = None) -> list[ProviderItem]:
        at, items = await self.call(lambda api, _token: api.search(source, query, page=page, ll=ll))
        return [replace(item, offers_token=self.tag(at, item.offers_token)) for item in items]

    async def locate(self, query: str) -> tuple[str, tuple[float, float]] | None:
        return (await self.call(lambda api, _token: api.locate(query)))[1]

    async def stores(self, token: str) -> list[Store]:
        answered = await self.call(lambda api, raw: api.stores(raw), token)
        return answered[1] if answered is not None else []


def calls_per_search(provider: Any, page: int) -> int:
    """Paid calls one search for `page` makes, on the API asked first. Google's
    Places API pages by token, so its page n is n calls (none past MAX_PAGES);
    the SERP APIs take the page number."""
    if isinstance(provider, Listings):
        provider = provider.first()
    if isinstance(provider, GooglePlaces):
        return page if page <= MAX_PAGES else 0
    return 1


def _google_key() -> str | None:
    from app.config import get_settings

    return getattr(get_settings(), "google_maps_api_key", None) or None


def _keys() -> tuple[str | None, str | None]:
    from app.config import get_settings

    settings = get_settings()
    return (getattr(settings, "search_api_key", None) or None,
            getattr(settings, "serp_api_key", None) or None)


def configured() -> bool:
    try:
        return any(_keys())
    except Exception:
        logger.warning("research provider check failed", exc_info=True)
        return False


def asks(provider: Any, token: str) -> bool:
    """Whether a store lookup with `token` would still be asked: not once the
    API that gave it has been dropped (its token means nothing to another)."""
    return not isinstance(provider, Listings) or provider.holds(token)


def choose_provider(source: str | None = None, *, transport: httpx.AsyncBaseTransport | None = None,
                    sleep: SleepFn = asyncio.sleep) -> Listings | None:
    """The APIs for a `source`, in order: Google's own for `places` when its
    key is set, then SearchAPI, then SerpApi; None with none of them."""
    google = _google_key() if source == "places" else None
    search_api, serp_api = _keys()
    apis = ([GooglePlaces(google, transport=transport, sleep=sleep)] if google else []) + (
        [SearchApi(search_api, transport=transport, sleep=sleep)] if search_api else []) + (
        [SerpApi(serp_api, transport=transport, sleep=sleep)] if serp_api else [])
    return Listings(apis) if apis else None
