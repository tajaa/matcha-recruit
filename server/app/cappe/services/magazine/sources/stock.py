"""Modern stock photos, free for any use: the CC0 collections Openverse
gathers from StockSnap.io, the WordPress Photo Directory and Nappy (about
86,000 photos, counted 2026-10-22), where a plain Openverse search mixes them
into half a billion Flickr pictures and museum scans.

The results are Openverse's own (source `openverse`), so they import, credit
and are re-checked at Openverse exactly as any Openverse picture is: nothing
new is stored, and no new account is needed. Unlike the archives it can be
browsed with no words, so the Studio's Photos tab opens full.
"""
from __future__ import annotations

from typing import Optional

from . import openverse
from .base import StockResult

NAME = "stock"
LABEL = "Free photos"
BROWSE = True
SEARCH_TTL = 86400  # the collections change slowly, and anonymous Openverse allows 200 searches a day
COLLECTIONS = ("stocksnap", "wordpress", "nappy")
LICENSES = ("cc0", "pdm")


async def search(query: str, page: int) -> list[StockResult]:
    return await openverse.search(query, page, collections=COLLECTIONS, licenses=LICENSES)


async def resolve(source_id: str) -> Optional[StockResult]:
    return await openverse.resolve(source_id)
