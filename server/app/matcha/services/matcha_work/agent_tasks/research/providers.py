"""Structured listings for research tasks: Google Maps, from Google itself.

For places and apartment buildings, a provider gives what a web search can't:
a rating, a point on the map and a link as data rather than prose a model
read. Those come in as findings whose fields are verified with origin
`provider`. Anything else (products, events) is found by the model's web
search (Brave) and read on its own page.

Google Maps comes straight from Google (`GooglePlaces`: the Places API (New)
Text Search with `GOOGLE_MAPS_API_KEY`, the Google Maps Platform key Tell-Us's
place search uses). Without that key there is no provider and a places task
is the web search alone. `choose_provider("places")` wraps it in `Listings`,
so a refused key or no quota is dropped for the phase and logged once, by
`search_apis`' rules. Only the query text (and, for an area, its map box)
leaves the server. Every call counts against the round's provider budget
(`chain.grant`).

Google Shopping (through SearchAPI, else SerpApi) and the SERP APIs' Google
Maps were taken out on 2026-10-18: Espresso's agents use Brave, Claude and
Google's own APIs, no search API.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable
from urllib.parse import parse_qsl, quote_plus, urlsplit

import httpx

from app.matcha.services.matcha_work import search_apis
from app.matcha.services.matcha_work.agent_card.schema import normalize_url
from app.matcha.services.matcha_work.search_apis import ProviderError, SleepFn  # noqa: F401  (phases and geo catch it here)

from . import fields as F
from .geo import point_of

logger = logging.getLogger(__name__)

MAX_RESULTS = 20


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
    # Google Maps: where it is, (lat, lng).
    point: tuple[float, float] | None = None


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


def _put(out: dict, key: str, raw: Any, *, quote: str, url: str | None, today: date, **money) -> None:
    made = F.entry(F.LIBRARY[key], raw, status="verified", origin="provider", today=today,
                   url=url, quote=quote, **money)
    if made is not None:
        out[key] = made


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
    hours = raw.get("hours")
    if isinstance(hours, str) and hours.strip():
        _put(out, "hours", hours, url=url, today=today, quote=f"Google Maps hours: {F.clean_text(hours, 200)}")
    return ProviderItem(
        kind="place", title=title, url=url, subtitle=address, provider="google_maps",
        provider_id=place_id, fields=out, point=point_of(raw.get("gps_coordinates")),
    )


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
    """A Places API place as a finding (`place_item`). A place Google marks
    closed for good is skipped."""
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

    async def search_pages(self, source: str, query: str, *, pages: int = 1,
                           ll: str | None = None) -> list[ProviderItem]:
        """Pages 1..`pages` (at most `MAX_PAGES`) in one walk of the page
        tokens: `pages` calls, where `search(page=n)` for each would be
        1 + 2 + … + n."""
        if source != "places":
            raise ValueError(f"{self.name} has no {source!r} search")
        body: dict = {"textQuery": query, "pageSize": MAX_RESULTS, "languageCode": "en"}
        box = map_box(ll)
        if box:
            body["locationRestriction"] = {"rectangle": box}
        today = self._today()
        items: list[ProviderItem] = []
        token = None
        for n in range(min(max(1, pages), MAX_PAGES)):
            if n and not token:
                break
            data = await self._post({**body, "pageToken": token} if token else body, SEARCH_MASK)
            token = data.get("nextPageToken")
            rows = data.get("places")
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
    """Google Places as a `search_apis.Fallback`: refused for good (a refused
    key, no quota), it is dropped for the phase and logged once."""

    label = "research listings"

    async def search(self, source: str, query: str, *, page: int = 1, ll: str | None = None) -> list[ProviderItem]:
        return (await self.call(lambda api, _token: api.search(source, query, page=page, ll=ll)))[1]

    async def search_pages(self, source: str, query: str, *, pages: int = 1,
                           ll: str | None = None) -> list[ProviderItem]:
        """Several pages in one walk of Google's page tokens (`search_pages`)."""
        return (await self.call(lambda api, _token: api.search_pages(source, query, pages=pages, ll=ll)))[1]

    async def locate(self, query: str) -> tuple[str, tuple[float, float]] | None:
        return (await self.call(lambda api, _token: api.locate(query)))[1]


def calls_per_search(provider: Any, page: int) -> int:
    """Paid calls one search for `page` makes. Google's Places API pages by
    token, so its page n is n calls (none past MAX_PAGES)."""
    return page if page <= MAX_PAGES else 0


def _google_key() -> str | None:
    from app.config import get_settings

    return getattr(get_settings(), "google_maps_api_key", None) or None


def choose_provider(source: str | None = None, *, transport: httpx.AsyncBaseTransport | None = None,
                    sleep: SleepFn = asyncio.sleep) -> Listings | None:
    """Google Places for `places` when `GOOGLE_MAPS_API_KEY` is set; None
    otherwise (every other source is the web search alone)."""
    google = _google_key() if source == "places" else None
    return Listings([GooglePlaces(google, transport=transport, sleep=sleep)]) if google else None
