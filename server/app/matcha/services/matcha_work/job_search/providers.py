"""Google Jobs listings through a search API: SearchAPI.io or SerpApi.

Both serve Google's job results as JSON (`engine=google_jobs`); only the field
names differ. SearchAPI (`SEARCH_API_KEY`) is tried first, then SerpApi
(`SERP_API_KEY`); with neither, job search is not offered. One that refuses
for good (a refused key, or no searches left this month) is dropped for the
rest of the search and the next is used (`FallbackJobs`); that is logged as
an error, so it shows in Admin → Server Errors.

Only the query and location leave the server: never the person's résumé or
name. Every call counts against the search's provider budget.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from . import normalize

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20.0
MAX_DESCRIPTION = 20_000


class ProviderError(Exception):
    """A search that could not be done. `fatal` when retrying cannot help
    (a refused key, no searches left), so the search should stop rather than
    retry."""

    def __init__(self, message: str, *, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


# What a listings API says when the account has no searches left. SearchAPI
# answers 429 "You have used all of the searches for the month. Please upgrade
# your plan on SearchApi.io."; SerpApi 429 "Your account has run out of
# searches."; Google 429 "Quota exceeded …".
_NO_SEARCHES_LEFT = re.compile(
    r"used all of the searches|run out of searches|out of (?:searches|credits)|upgrade your plan|quota", re.I,
)


def out_of_searches(response: httpx.Response) -> str | None:
    """The API's own words when it refused because the account has no
    searches left (a 402, or a 429 that says so); None otherwise, so a plain
    429 (too many at once) is still tried again."""
    if response.status_code not in (402, 429):
        return None
    try:
        body = response.json()
    except ValueError:
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        error = error.get("message") or error.get("status")
    text = normalize.clean_text(error, 200) if error else ""
    if response.status_code == 402 or _NO_SEARCHES_LEFT.search(text):
        return text or "no searches left"
    return None


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


SleepFn = Callable[[float], Awaitable[None]]


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
        last: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport) as client:
                    response = await client.get(self.base_url, params=params)
            except httpx.HTTPError as exc:
                last = exc
            else:
                if response.status_code in (401, 403):
                    raise ProviderError(f"{self.name} refused the API key", fatal=True)
                spent = out_of_searches(response)
                if spent is not None:
                    raise ProviderError(f"{self.name} has no searches left ({spent})", fatal=True)
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
                    return self._parse(data)
            if attempt == 0:
                await self._sleep(2.0)
        raise ProviderError(f"{self.name} did not answer: {type(last).__name__}")


def _no_results(data: dict) -> bool:
    error = str(data.get("error") or "")
    return "hasn't returned any results" in error or "no results" in error.lower()


class SearchApiJobs(_JobsApi):
    name = "SearchAPI"
    base_url = "https://www.searchapi.io/api/v1/search"

    def _parse(self, data: dict) -> tuple[list[Posting], str | None]:
        if data.get("error") and not _no_results(data):
            raise ProviderError(f"SearchAPI: {str(data['error'])[:200]}")
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
        if data.get("error") and not _no_results(data):
            raise ProviderError(f"SerpApi: {str(data['error'])[:200]}")
        postings = []
        for raw in data.get("jobs_results") or []:
            if isinstance(raw, dict):
                links = _links(raw.get("apply_options"), url_key="link", source_key="title")
                posting = _posting(raw, links=links, share_url=raw.get("share_link"))
                if posting:
                    postings.append(posting)
        pagination = data.get("serpapi_pagination") if isinstance(data.get("serpapi_pagination"), dict) else {}
        return postings, (pagination.get("next_page_token") or None)


class FallbackJobs:
    """The listings APIs in order. One that refuses for good (a refused key,
    no searches left) is dropped for the rest of the search and the next is
    used; with none left, its error is raised. A page token says which API
    gave it, since one API's token means nothing to another: a query whose
    pages came from a dropped API ends there."""

    def __init__(self, apis: list[_JobsApi]):
        self.apis = list(apis)
        self._at = 0
        self._last: ProviderError | None = None

    @property
    def name(self) -> str:
        return self.apis[min(self._at, len(self.apis) - 1)].name

    async def search(self, query: str, location: str | None = None, *,
                     page_token: str | None = None) -> tuple[list[Posting], str | None]:
        given_by, _, token = (page_token or "").partition(":")
        while self._at < len(self.apis):
            at = self._at
            if page_token and given_by != str(at):
                return [], None
            try:
                postings, following = await self.apis[at].search(query, location, page_token=token or None)
            except ProviderError as exc:
                if not exc.fatal:
                    raise
                self._last = exc
                if self._at == at:  # not dropped already by a query running alongside
                    self._at = at + 1
                    instead = (f"using {self.apis[at + 1].name} instead" if at + 1 < len(self.apis)
                               else "no other job listings API is set up")
                    logger.error("job listings: %s; %s", exc, instead)
                continue
            return postings, (f"{at}:{following}" if following else None)
        raise self._last or ProviderError("no job listings API is set up", fatal=True)


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
