"""NASA's image library (images-api.nasa.gov).

NASA's own imagery is not copyrighted, but the library also holds pictures
NASA may use and we may not: anything whose description or credit names a
copyright holder or says "courtesy" is left out. Each item's files are listed
in its manifest (`href`); we take the largest web size it has (`~large`,
then `~medium`, then the original), never a guessed name — not every item has
every size.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote

from .base import PAGE_SIZE, StockResult, clean, get_json, https
from .credit import credit_line

NAME = "nasa"
LABEL = "NASA"
API = "https://images-api.nasa.gov"
_THIRD_PARTY = re.compile(r"©|\(c\)|copyright|courtesy of|courtesy:|all rights reserved", re.I)
_SIZES = ("~large.", "~medium.", "~orig.", "~small.")


def normalize(item: dict[str, Any]) -> Optional[StockResult]:
    data = (item.get("data") or [{}])[0]
    if not isinstance(data, dict) or data.get("media_type") not in (None, "image"):
        return None
    nasa_id = clean(data.get("nasa_id"), 200)
    if not nasa_id:
        return None
    text = " ".join(str(data.get(k) or "") for k in ("description", "photographer", "secondary_creator", "title"))
    if _THIRD_PARTY.search(text):
        return None
    preview = next((https(link.get("href")) for link in item.get("links") or []
                    if isinstance(link, dict) and link.get("rel") in ("preview", "alternate") and link.get("href")), "")
    center = clean(data.get("center"), 40)
    who = clean(data.get("photographer") or data.get("secondary_creator"), 120)
    creator = "/".join(p for p in (center, who) if p)
    result = StockResult(
        source=NAME, source_id=nasa_id, title=clean(data.get("title"), 300), creator=creator,
        license="pdm", license_version="", license_url="https://www.nasa.gov/nasa-brand-center/images-and-media/",
        provider_label="NASA", landing_url=f"https://images.nasa.gov/details/{quote(nasa_id, safe='')}",
        image_url=https(item.get("href")), thumb_url=preview,
    )
    result.credit_line = credit_line(result)
    return result if result.thumb_url else None


async def search(query: str, page: int) -> list[StockResult]:
    data = await get_json(f"{API}/search", {"q": query, "media_type": "image", "page_size": PAGE_SIZE, "page": page + 1})
    items = ((data or {}).get("collection") or {}).get("items") or []
    return [r for r in (normalize(i) for i in items if isinstance(i, dict)) if r]


def best_file(manifest: Any) -> str:
    files = [https(u) for u in manifest if isinstance(u, str)] if isinstance(manifest, list) else []
    for size in _SIZES:
        for f in files:
            if size in f and f.lower().endswith((".jpg", ".jpeg", ".png")):
                return f
    return ""


async def resolve(source_id: str) -> Optional[StockResult]:
    data = await get_json(f"{API}/search", {"nasa_id": source_id, "media_type": "image"})
    items = ((data or {}).get("collection") or {}).get("items") or []
    result = normalize(items[0]) if items and isinstance(items[0], dict) else None
    if result is None or result.source_id != source_id:
        return None
    # The search's `href` is the item's file manifest, not a picture.
    result.image_url = best_file(await get_json(result.image_url)) if result.image_url else ""
    return result if result.image_url else None
