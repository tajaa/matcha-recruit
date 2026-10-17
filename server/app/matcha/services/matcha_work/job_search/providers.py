"""Google Jobs listings through a search API: SearchAPI.io or SerpApi.

Both serve Google's job results as JSON (`engine=google_jobs`); only the field
names differ. SearchAPI (`SEARCH_API_KEY`) is tried first, then SerpApi
(`SERP_API_KEY`); with neither, job search is not offered. Requests, retries
and moving to the next API (one that refuses for good, or is down) are
`search_apis`' (`FallbackJobs` is its `Fallback`).

Only the query and location leave the server: never the person's résumé or
name. Every call counts against the search's provider budget.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from .. import search_apis
from ..search_apis import ProviderError, SleepFn
from . import normalize

logger = logging.getLogger(__name__)

MAX_DESCRIPTION = 20_000


@dataclass
class Posting:
    title: str
    company: str
    location: str = ""
    via: str = ""
    description: str = ""
    salary_text: str | None = None
    posted_text: str | None = None
    schedule_type: str | None = None
    remote: bool | None = None
    highlights: list[dict] = field(default_factory=list)
    apply_links: list[dict] = field(default_factory=list)  # [{url, source}]
    share_url: str | None = None
    provider_job_id: str | None = None


def _str(value: Any, limit: int = 300) -> str:
    return normalize.clean_text(value, limit) if value is not None else ""


def _highlights(raw: Any) -> list[dict]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        items = [_str(i, 400) for i in (item.get("items") or []) if isinstance(i, str)][:12]
        if items:
            out.append({"title": _str(item.get("title"), 80), "items": items})
    return out[:6]


def _links(raw: Any, *, url_key: str, source_key: str) -> list[dict]:
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        url = normalize.http_url(item.get(url_key))
        if url and url not in seen:
            seen.add(url)
            out.append({"url": url, "source": _str(item.get(source_key), 80)})
    return out[:8]


def _posting(raw: dict, *, links: list[dict], share_url: Any) -> Posting | None:
    title = _str(raw.get("title"), 200)
    company = _str(raw.get("company_name"), 200)
    if not title or not company:
        return None
    ext = raw.get("detected_extensions") if isinstance(raw.get("detected_extensions"), dict) else {}
    location = _str(raw.get("location"), 200)
    remote = normalize.is_remote(location, flag=True if ext.get("work_from_home") else None)
    return Posting(
        title=title,
        company=company,
        location=location,
        via=_str(raw.get("via"), 120),
        description=str(raw.get("description") or "")[:MAX_DESCRIPTION],
        salary_text=_str(ext.get("salary"), 120) or None,
        posted_text=_str(ext.get("posted_at"), 60) or None,
        schedule_type=_str(ext.get("schedule_type"), 60) or None,
        remote=remote,
        highlights=_highlights(raw.get("job_highlights")),
        apply_links=links,
        share_url=normalize.http_url(share_url),
        provider_job_id=_str(raw.get("job_id"), 2000) or None,
    )


class _JobsApi:
    name = ""
    base_url = ""

    def __init__(self, key: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 sleep: SleepFn = asyncio.sleep):
        self._key = key
        self._transport = transport
        self._sleep = sleep

    def _params(self, query: str, location: str | None, page_token: str | None) -> dict:
        params = {"engine": "google_jobs", "q": query, "api_key": self._key}
        if location:
            params["location"] = location
        if page_token:
            params["next_page_token"] = page_token
        return params

    def _parse(self, data: dict) -> tuple[list[Posting], str | None]:  # pragma: no cover - abstract
        raise NotImplementedError

    async def search(self, query: str, location: str | None = None, *,
                     page_token: str | None = None) -> tuple[list[Posting], str | None]:
        """One page of postings and the token for the next page (or None)."""
        params = self._params(query, location, page_token)
        data = await search_apis.answer(self.name, lambda client: client.get(self.base_url, params=params),
                                        transport=self._transport, sleep=self._sleep, sku=params["engine"])
        error = search_apis.result_error(data)
        if error:
            raise ProviderError(f"{self.name}: {error[:200]}")
        return self._parse(data)


class SearchApiJobs(_JobsApi):
    name = "SearchAPI"
    base_url = "https://www.searchapi.io/api/v1/search"

    def _parse(self, data: dict) -> tuple[list[Posting], str | None]:
        postings = []
        for raw in data.get("jobs") or []:
            if isinstance(raw, dict):
                links = _links(raw.get("apply_links"), url_key="link", source_key="source")
                posting = _posting(raw, links=links, share_url=raw.get("sharing_link"))
                if posting:
                    postings.append(posting)
        pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
        return postings, (pagination.get("next_page_token") or None)


class SerpApiJobs(_JobsApi):
    name = "SerpApi"
    base_url = "https://serpapi.com/search.json"

    def _parse(self, data: dict) -> tuple[list[Posting], str | None]:
        postings = []
        for raw in data.get("jobs_results") or []:
            if isinstance(raw, dict):
                links = _links(raw.get("apply_options"), url_key="link", source_key="title")
                posting = _posting(raw, links=links, share_url=raw.get("share_link"))
                if posting:
                    postings.append(posting)
        pagination = data.get("serpapi_pagination") if isinstance(data.get("serpapi_pagination"), dict) else {}
        return postings, (pagination.get("next_page_token") or None)


class FallbackJobs(search_apis.Fallback):
    """SearchAPI then SerpApi (`search_apis.Fallback`). A page token is marked
    with the API that gave it: a query whose pages came from an API dropped
    since ends there."""

    label = "job listings"

    async def search(self, query: str, location: str | None = None, *,
                     page_token: str | None = None) -> tuple[list[Posting], str | None]:
        answered = await self.call(lambda api, token: api.search(query, location, page_token=token), page_token)
        if answered is None:
            return [], None
        at, (postings, following) = answered
        return postings, self.tag(at, following)


def _keys() -> tuple[str | None, str | None]:
    from app.config import get_settings

    settings = get_settings()
    return (getattr(settings, "search_api_key", None) or None,
            getattr(settings, "serp_api_key", None) or None)


def choose_provider(*, transport: httpx.AsyncBaseTransport | None = None,
                    sleep: SleepFn = asyncio.sleep) -> FallbackJobs | None:
    """SearchAPI then SerpApi, whichever have keys; None with neither."""
    search_api, serp_api = _keys()
    apis = ([SearchApiJobs(search_api, transport=transport, sleep=sleep)] if search_api else []) + (
        [SerpApiJobs(serp_api, transport=transport, sleep=sleep)] if serp_api else [])
    return FallbackJobs(apis) if apis else None


def configured() -> bool:
    try:
        return any(_keys())
    except Exception:
        logger.warning("job search provider check failed", exc_info=True)
        return False
