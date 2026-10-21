"""What every open-image source returns, and the plumbing they share.

A search result (`StockResult`) carries what the Library shows and what an
import stores: the picture's address at its archive, its creator, its license
and the credit line we print. Only licenses that allow commercial use and
cropping are kept (`ALLOWED_LICENSES`: CC0, public domain, CC BY, CC BY-SA) —
magazines can be paid, and a cover crop is an adaptation — and nothing an
archive marks as mature. Each source checks this itself; `allowed()` is the
last word, and the import worker asks the source again before it downloads.

Provider calls go through `core.safe_fetch.fetch_public` like any fetch whose
address we don't fully control: the hosts are fixed, but redirects and the
image URLs inside a response are not.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import urlencode

from .....core.services.redis_cache import cache_get, cache_set, get_redis_cache
from .....core.services.safe_fetch import fetch_public

logger = logging.getLogger(__name__)

ALLOWED_LICENSES = frozenset({"cc0", "pdm", "by", "by-sa"})
USER_AGENT = "Gummfit/1.0 (+https://gummfit.com; magazines)"
MAX_JSON_BYTES = 3 * 1024 * 1024
PAGE_SIZE = 20
SEARCH_TTL = 3600
RESOLVE_TTL = 86400


class SourceError(RuntimeError):
    """The archive didn't answer usefully (down, throttled, changed shape)."""


@dataclass
class StockResult:
    source: str
    source_id: str
    title: str
    creator: str
    license: str
    license_version: str
    license_url: str
    provider_label: str
    landing_url: str
    image_url: str
    thumb_url: str
    creator_url: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    mature: bool = False
    credit_line: str = field(default="")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StockResult":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})


def allowed(result: StockResult) -> bool:
    return result.license in ALLOWED_LICENSES and not result.mature and bool(result.image_url)


def clean(text: Any, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


def https(url: Any) -> str:
    """An archive URL as https (NASA's manifests list http://), or ""."""
    u = str(url or "").strip()
    if u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    return u if u.startswith("https://") else ""


async def get_json(url: str, params: Optional[dict[str, Any]] = None, *, timeout: float = 20.0) -> Any:
    full = f"{url}?{urlencode(params)}" if params else url
    try:
        res = await fetch_public(full, max_bytes=MAX_JSON_BYTES, accept="application/json", gzip=True,
                                 total_timeout=timeout)
    except Exception as exc:  # unsafe host, network error, timeout
        raise SourceError(f"{type(exc).__name__}") from exc
    if res.status == 404:
        return None
    if res.status != 200 or res.truncated:
        raise SourceError(f"HTTP {res.status}")
    try:
        return json.loads(res.body)
    except ValueError as exc:
        raise SourceError("not JSON") from exc


def _key(*parts: Any) -> str:
    digest = hashlib.sha1("\x1f".join(str(p) for p in parts).encode()).hexdigest()
    return f"cappe:stock:{digest}"


async def cached(kind: str, parts: tuple, ttl: int, load):
    """`load()` once per `ttl`, shared by every account (archive data is public)."""
    redis = get_redis_cache()
    key = _key(kind, *parts)
    if redis:
        hit = await cache_get(redis, key)
        if hit is not None:
            return hit
    value = await load()
    if redis and value is not None:
        await cache_set(redis, key, value, ttl=ttl)
    return value
