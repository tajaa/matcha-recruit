"""A finding's own page, never Google's.

Research tasks find things with Brave and Claude and read them on their own
pages; nothing comes from a Google API. Findings from before 2026-10-18 may
still link to a Google Shopping or Maps page, so Buy and Apply unwrap
Google's redirects and refuse Google's own pages (`store_link`).
"""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlsplit

from app.matcha.services.matcha_work.agent_card.schema import normalize_url

# Ad-click and tracking hosts: following one of these registers a paid click.
AD_HOSTS = ("googleadservices.com", "doubleclick.net", "googlesyndication.com", "google-analytics.com")


def _http(url: Any) -> str | None:
    return url.strip() if isinstance(url, str) and normalize_url(url) else None


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
