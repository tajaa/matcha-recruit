"""SerpApi (Google Search) provider behind the radar's future-provider seam."""
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from ....config import get_settings
from .prompt import SearchQuery


@dataclass(frozen=True)
class SearchResult:
    mentions: list[dict]
    grounding_uris: list[str]
    grounding_resolved: int


class MentionProvider(Protocol):
    async def search(self, query: SearchQuery) -> SearchResult: ...


_HOST_PLATFORMS = {
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "x.com": "x",
    "twitter.com": "x",
}


def _platform_for_url(url: str) -> str | None:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return _HOST_PLATFORMS.get(host)


def _organic_results_to_mentions(payload: dict, match_terms: list[str]) -> SearchResult:
    lowered_terms = [term.lower() for term in match_terms if term]
    mentions: list[dict] = []
    uris: list[str] = []
    for result in payload.get("organic_results", []):
        if not isinstance(result, dict):
            continue
        url = result.get("link")
        if not isinstance(url, str):
            continue
        platform = _platform_for_url(url)
        if platform is None:
            continue
        snippet = result.get("snippet") if isinstance(result.get("snippet"), str) else ""
        title = result.get("title") if isinstance(result.get("title"), str) else ""
        haystack = f"{title} {snippet}".lower()
        matched = [term for term in lowered_terms if term in haystack]
        uris.append(url)
        mentions.append({
            "platform": platform,
            "url": url,
            "author_handle": None,
            "excerpt": snippet.strip(),
            "matched_terms": matched,
            "confidence": 60 if matched else 40,
            "corroborated": True,
        })
    resolved = list(dict.fromkeys(uris))
    return SearchResult(mentions=mentions, grounding_uris=resolved, grounding_resolved=len(resolved))


class SerpApiProvider:
    async def search(self, query: SearchQuery) -> SearchResult:
        settings = get_settings()
        if not settings.serp_api_key:
            raise RuntimeError("SERP_API_KEY is required for shoutout scans.")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://serpapi.com/search",
                params={
                    "engine": "google",
                    "q": query.q,
                    "num": query.num,
                    "api_key": settings.serp_api_key,
                },
            )
            response.raise_for_status()
        return _organic_results_to_mentions(response.json(), query.match_terms)
