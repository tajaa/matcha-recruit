"""The Metropolitan Museum of Art's open collection
(collectionapi.metmuseum.org): its public-domain works, CC0.

Searching is two steps: `/v1.1/search` (the v1 search was retired on
2026-10-01) returns object ids, then each object is read for its image and
rights. The search's `isPublicDomain=true` filter is not reliable — checked
2026-10-21, most results came back copyrighted — so every object's own
`isPublicDomain` decides. Objects are read a few at a time and cached for a
week; the Met asks for fewer than 80 requests a second.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from .base import PAGE_SIZE, StockResult, cached, clean, get_json, https
from .credit import credit_line

NAME = "met"
LABEL = "The Met"
API = "https://collectionapi.metmuseum.org/public/collection"
OBJECT_TTL = 7 * 86400
_PARALLEL = 5


def normalize(obj: dict[str, Any]) -> Optional[StockResult]:
    if not obj.get("isPublicDomain"):
        return None
    image = https(obj.get("primaryImage"))
    if not image or not obj.get("objectID"):
        return None
    title = clean(obj.get("title"), 300)
    if obj.get("objectDate"):
        title = clean(f"{title}, {obj['objectDate']}", 300)
    result = StockResult(
        source=NAME, source_id=str(obj["objectID"]), title=title, creator=clean(obj.get("artistDisplayName"), 300),
        license="cc0", license_version="1.0", license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        provider_label="The Metropolitan Museum of Art", landing_url=https(obj.get("objectURL")),
        image_url=image, thumb_url=https(obj.get("primaryImageSmall")) or image,
        creator_url=https(obj.get("artistWikidata_URL")),
    )
    result.credit_line = credit_line(result)
    return result


async def _object(object_id: int | str) -> Optional[dict]:
    return await cached("met-object", (object_id,), OBJECT_TTL,
                        lambda: get_json(f"{API}/v1/objects/{object_id}"))


async def search(query: str, page: int) -> list[StockResult]:
    data = await get_json(f"{API}/v1.1/search", {
        "q": query, "hasImages": "true", "isPublicDomain": "true", "limit": PAGE_SIZE, "offset": page * PAGE_SIZE,
    })
    ids = [i for i in ((data or {}).get("objectIDs") or []) if isinstance(i, int)][:PAGE_SIZE]
    gate = asyncio.Semaphore(_PARALLEL)

    async def one(object_id: int) -> Optional[StockResult]:
        async with gate:
            try:
                obj = await _object(object_id)
            except Exception:  # noqa: BLE001 — one bad object never sinks the page
                return None
        return normalize(obj) if isinstance(obj, dict) else None

    return [r for r in await asyncio.gather(*(one(i) for i in ids)) if r]


async def resolve(source_id: str) -> Optional[StockResult]:
    if not source_id.isdigit():
        return None
    obj = await get_json(f"{API}/v1/objects/{source_id}")
    return normalize(obj) if isinstance(obj, dict) else None
