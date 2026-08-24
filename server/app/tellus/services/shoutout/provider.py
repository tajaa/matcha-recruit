"""SerpApi (Google Search) provider behind the radar's future-provider seam."""
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from ....config import get_settings
from .grounding import is_post_url
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


def _author_handle_from_source(source: str | None) -> str | None:
    """'Instagram · faelpt' -> 'faelpt'; 'Instagram' -> None; rejects display names with spaces."""
    if not isinstance(source, str) or "·" not in source:
        return None
    handle = source.split("·", 1)[1].strip().lstrip("@")
    if not handle or " " in handle:
        return None
    return handle.lower()


_COUNT_RE = re.compile(r"^([\d,.]+)\s*([KMB]?)\+?$", re.IGNORECASE)
_MULTIPLIERS = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def _parse_count(token: str) -> int | None:
    """'12K+' -> 12000, '1.2K+' -> 1200, '291.4M+' -> 291_400_000, '1,234' -> 1234."""
    match = _COUNT_RE.match(token.strip())
    if not match:
        return None
    number, suffix = match.groups()
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    return int(value * _MULTIPLIERS[suffix.upper()])


def _engagement_from_displayed_link(displayed_link: str | None) -> tuple[int | None, str | None]:
    """'12K+ likes · 6 days ago' -> (12000, '6 days ago'); '291.4M+ followers' -> (None, None)."""
    if not isinstance(displayed_link, str) or "like" not in displayed_link.lower():
        return None, None
    parts = [part.strip() for part in displayed_link.split("·")]
    like_count = None
    for part in parts:
        words = part.split()
        if len(words) >= 2 and words[1].lower().startswith("like"):
            like_count = _parse_count(words[0])
            break
    posted_age = parts[1] if len(parts) > 1 and like_count is not None else None
    return like_count, posted_age


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
        if platform is None or not is_post_url(platform, url):
            continue
        snippet = result.get("snippet") if isinstance(result.get("snippet"), str) else ""
        title = result.get("title") if isinstance(result.get("title"), str) else ""
        haystack = f"{title} {snippet}".lower()
        matched = [term for term in lowered_terms if term in haystack]
        like_count, posted_age = _engagement_from_displayed_link(result.get("displayed_link"))
        uris.append(url)
        mentions.append({
            "platform": platform,
            "url": url,
            "author_handle": _author_handle_from_source(result.get("source")),
            "excerpt": snippet.strip(),
            "matched_terms": matched,
            "confidence": 60 if matched else 40,
            "corroborated": True,
            "like_count": like_count,
            "posted_age": posted_age,
            "stats_source": "search" if like_count is not None else None,
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
