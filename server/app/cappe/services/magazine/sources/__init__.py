"""Open-image sources for the magazine Library (cappemag03).

`SOURCES` is the registry the routes and the import worker go through:
`search(source, query, page)` (cached an hour, shared across accounts — the
data is public) and `resolve(source, source_id)` (the picture looked up again
at its archive, uncached when the worker asks so a license that changed is
caught). Results are filtered by `base.allowed` on the way out of both.
"""
from __future__ import annotations

from types import ModuleType
from typing import Optional

from . import met, nasa, openverse, smithsonian
from .base import RESOLVE_TTL, SEARCH_TTL, SourceError, StockResult, allowed, cached

SOURCES: dict[str, ModuleType] = {m.NAME: m for m in (openverse, smithsonian, met, nasa)}
LABELS = {name: m.LABEL for name, m in SOURCES.items()}
MAX_QUERY = 120
MAX_PAGE = 20

__all__ = ["SOURCES", "LABELS", "SourceError", "StockResult", "search", "resolve", "allowed"]


def _module(source: str) -> ModuleType:
    if source not in SOURCES:
        raise KeyError(source)
    return SOURCES[source]


async def search(source: str, query: str, page: int = 0) -> list[StockResult]:
    module = _module(source)
    q = " ".join(query.split())[:MAX_QUERY]
    if not q:
        return []
    page = max(0, min(int(page), MAX_PAGE))

    async def load():
        return [r.to_dict() for r in await module.search(q, page)]

    rows = await cached("search", (source, q.lower(), page), SEARCH_TTL, load) or []
    return [r for r in (StockResult.from_dict(d) for d in rows) if allowed(r)]


async def resolve(source: str, source_id: str, *, fresh: bool = False) -> Optional[StockResult]:
    module = _module(source)
    if fresh:
        result = await module.resolve(source_id)
    else:
        async def load():
            found = await module.resolve(source_id)
            return found.to_dict() if found else None

        data = await cached("resolve", (source, source_id), RESOLVE_TTL, load)
        result = StockResult.from_dict(data) if data else None
    return result if result and allowed(result) else None
