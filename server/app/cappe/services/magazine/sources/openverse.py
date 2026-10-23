"""Openverse (api.openverse.org): Creative Commons and public-domain images
gathered from Flickr, Wikimedia Commons and other collections.

Anonymous requests work but are throttled; with `OPENVERSE_CLIENT_ID` and
`OPENVERSE_CLIENT_SECRET` set (an app registered at
`POST /v1/auth_tokens/register/`) we exchange them for a bearer token
(client-credentials grant), cached in Redis until shortly before it expires.

Openverse says its license data is gathered, not guaranteed, so we keep the
page the picture came from (`foreign_landing_url`) and print it in the credit
link; a report takes down anything that turns out wrong.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from .....config import get_settings
from .....core.services.redis_cache import cache_get, cache_set, get_redis_cache
from .base import ALLOWED_LICENSES, PAGE_SIZE, USER_AGENT, SourceError, StockResult, clean, https
from .credit import credit_line

logger = logging.getLogger(__name__)

NAME = "openverse"
LABEL = "Openverse"
API = "https://api.openverse.org/v1"
_TOKEN_KEY = "cappe:stock:openverse:token"
_PROVIDERS = {"flickr": "Flickr", "wikimedia": "Wikimedia Commons", "stocksnap": "StockSnap.io",
              "wordpress": "WordPress Photo Directory", "nappy": "Nappy"}
# Anonymous requests may not page past 240 results (HTTP 401 beyond it,
# checked 2026-10-21); a registered app goes deeper.
ANON_PAGES = 240 // PAGE_SIZE
# An uncached search took 10–38 s on 2026-10-22, so 20 s timed out real ones.
TIMEOUT = 40
_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _provider(item: dict[str, Any]) -> str:
    key = item.get("source") or item.get("provider") or ""
    return _PROVIDERS.get(key, clean(key.replace("_", " ").title(), 80) or LABEL)


def normalize(item: dict[str, Any]) -> Optional[StockResult]:
    """A result we would print, or None (wrong license, mature, no image)."""
    license_ = (item.get("license") or "").lower()
    if license_ not in ALLOWED_LICENSES or item.get("mature"):
        return None
    image = https(item.get("url"))
    if not image or not item.get("id"):
        return None
    result = StockResult(
        source=NAME, source_id=str(item["id"]), title=clean(item.get("title"), 300),
        creator=clean(item.get("creator"), 300), creator_url=https(item.get("creator_url")),
        license=license_, license_version=clean(item.get("license_version"), 8),
        license_url=https(item.get("license_url")), provider_label=_provider(item),
        landing_url=https(item.get("foreign_landing_url")), image_url=image,
        thumb_url=https(item.get("thumbnail")) or image,
        width=item.get("width") if isinstance(item.get("width"), int) else None,
        height=item.get("height") if isinstance(item.get("height"), int) else None,
        mature=bool(item.get("mature")),
        tags=[clean(t.get("name"), 40) for t in (item.get("tags") or [])[:12]
              if isinstance(t, dict) and clean(t.get("name"), 40)],
    )
    result.credit_line = credit_line(result)
    return result


async def _headers() -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    settings = get_settings()
    if not (settings.openverse_client_id and settings.openverse_client_secret):
        return headers
    redis = get_redis_cache()
    token = await cache_get(redis, _TOKEN_KEY) if redis else None
    if not token:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(f"{API}/auth_tokens/token/", data={
                    "grant_type": "client_credentials", "client_id": settings.openverse_client_id,
                    "client_secret": settings.openverse_client_secret,
                }, headers={"User-Agent": USER_AGENT})
            res.raise_for_status()
            data = res.json()
            token = data["access_token"]
            if redis:
                await cache_set(redis, _TOKEN_KEY, token, ttl=max(60, int(data.get("expires_in", 3600)) - 120))
        except Exception as exc:  # noqa: BLE001 — fall back to anonymous, never fail the search
            logger.warning("openverse token exchange failed (%s); searching anonymously", type(exc).__name__)
            return headers
    headers["Authorization"] = f"Bearer {token}"
    return headers


async def _get(path: str, params: Optional[dict[str, Any]] = None,
               headers: Optional[dict[str, str]] = None) -> Any:
    # Openverse is the one source that wants a header (the token), so it uses
    # httpx to its fixed host; image URLs inside the response still go through
    # the guarded fetcher when they are downloaded.
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.get(f"{API}{path}", params=params, headers=headers or await _headers())
    except httpx.HTTPError as exc:
        raise SourceError(type(exc).__name__) from exc
    if res.status_code == 404:
        return None
    if res.status_code != 200:
        raise SourceError(f"HTTP {res.status_code}")
    try:
        return res.json()
    except ValueError as exc:
        raise SourceError("not JSON") from exc


async def search(query: str, page: int, *, collections: tuple[str, ...] = (),
                 licenses: tuple[str, ...] = ()) -> list[StockResult]:
    """One page for `query` (none: Openverse's own order), narrowed to
    `collections` (Openverse source names) and `licenses` when given."""
    headers = await _headers()
    if page >= ANON_PAGES and "Authorization" not in headers:
        return []
    params = {"page": page + 1, "page_size": PAGE_SIZE, "mature": "false",
              "license": ",".join(sorted(set(licenses) & ALLOWED_LICENSES if licenses else ALLOWED_LICENSES))}
    if query:
        params["q"] = query
    if collections:
        params["source"] = ",".join(collections)
    data = await _get("/images/", params, headers)
    items = (data or {}).get("results") or []
    return [r for r in (normalize(i) for i in items if isinstance(i, dict)) if r]


async def resolve(source_id: str) -> Optional[StockResult]:
    if not _ID.fullmatch(source_id or ""):
        return None
    data = await _get(f"/images/{source_id}/")
    return normalize(data) if isinstance(data, dict) else None
