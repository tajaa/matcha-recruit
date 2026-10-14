"""Structured listings for research tasks: Google Shopping and Google Maps via SearchAPI.

For products and places, a provider gives what a web search can't: a price, a
rating and a link as data rather than prose a model read. Those come in as
findings whose fields are verified with origin `provider`, the way Google Jobs
is for job search. Anything else (homes, events) has no provider and is found
by the model with web search.

Through SearchAPI (`SEARCH_API_KEY`) when set, else SerpApi (`SERP_API_KEY`),
the same keys job search uses: both serve Google's results as JSON with
nearly the same fields. Only the query text leaves the server. Every call
counts against the round's provider budget (`chain.grant`).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Awaitable, Callable
from urllib.parse import quote_plus

import httpx

from app.matcha.services.matcha_work.agent_card.schema import normalize_url

from . import fields as F

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20.0
MAX_RESULTS = 20
KINDS = {"shopping": "product", "places": "place"}


class ProviderError(Exception):
    """A search that could not be done. `fatal` when retrying cannot help."""

    def __init__(self, message: str, *, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


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


def _http(url: Any) -> str | None:
    return url.strip() if isinstance(url, str) and normalize_url(url) else None


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
    )


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
    )


SleepFn = Callable[[float], Awaitable[None]]


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

    async def _get(self, params: dict) -> dict:
        last: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport) as client:
                    response = await client.get(self.base_url, params={**params, "api_key": self._key})
            except httpx.HTTPError as exc:
                last = exc
            else:
                if response.status_code in (401, 403):
                    raise ProviderError(f"{self.name} refused the API key", fatal=True)
                if response.status_code == 429 or response.status_code >= 500:
                    last = ProviderError(f"{self.name} answered {response.status_code}")
                elif response.status_code >= 400:
                    raise ProviderError(f"{self.name} answered {response.status_code}")
                else:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise ProviderError(f"{self.name} returned something other than JSON") from exc
                    if not isinstance(data, dict):
                        raise ProviderError(f"{self.name} returned an unexpected shape")
                    error = str(data.get("error") or "")
                    if error and "hasn't returned any results" not in error and "no results" not in error.lower():
                        raise ProviderError(f"{self.name}: {error[:200]}")
                    return data
            if attempt == 0:
                await self._sleep(2.0)
        raise ProviderError(f"{self.name} did not answer: {type(last).__name__}")

    async def search(self, source: str, query: str, *, page: int = 1) -> list[ProviderItem]:
        """One page of `shopping` or `places` results for the query text."""
        today = self._today()
        if source == "shopping":
            data = await self._get(self._params("google_shopping", query, page))
            rows, build = data.get("shopping_results"), shopping_item
        elif source == "places":
            data = await self._get(self._params("google_maps", query, page))
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


class SearchApi(_Api):
    name = "SearchAPI"
    base_url = "https://www.searchapi.io/api/v1/search"

    def _params(self, engine: str, query: str, page: int) -> dict:
        return {"engine": engine, "q": query, "page": page}


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


def choose_provider(*, transport: httpx.AsyncBaseTransport | None = None,
                    sleep: SleepFn = asyncio.sleep) -> _Api | None:
    search_api, serp_api = _keys()
    if search_api:
        return SearchApi(search_api, transport=transport, sleep=sleep)
    if serp_api:
        return SerpApi(serp_api, transport=transport, sleep=sleep)
    return None
