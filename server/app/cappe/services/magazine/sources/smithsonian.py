"""Smithsonian Open Access (api.si.edu): CC0 objects from the Smithsonian's
museums, each with its own images.

A search asks for objects with images (`online_visual_material:true`), and an
object can carry several; we keep each image whose own `usage.access` is CC0
(an object's record can be CC0 while one of its images isn't). The delivery
service resizes on request (`&max=`), so we never pull a 3,000 px TIFF.

Needs an api.data.gov key (`SMITHSONIAN_API_KEY`); without one the throttled
`DEMO_KEY` is used, which is fine for development and not for production.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote

from .....config import get_settings
from .base import PAGE_SIZE, StockResult, clean, get_json, https
from .credit import credit_line

NAME = "smithsonian"
LABEL = "Smithsonian"
API = "https://api.si.edu/openaccess/api/v1.0"
DELIVERY = "https://ids.si.edu/ids/deliveryService"
IMAGE_MAX = 2048
THUMB_MAX = 400


def _key() -> str:
    return get_settings().smithsonian_api_key or "DEMO_KEY"


# "James McNeill Whistler, born Lowell, MA 1834-died London, England 1903" → the name.
_LIFE = re.compile(r",\s*(?:born|b\.|died|d\.|active)\b.*$", re.I)


def _first(entries: Any) -> str:
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        return clean(_LIFE.sub("", str(entries[0].get("content") or "")), 300)
    return ""


def _size(media: dict) -> tuple[Optional[int], Optional[int]]:
    for res in media.get("resources") or []:
        w, h = res.get("width"), res.get("height")
        if isinstance(w, int) and isinstance(h, int) and w and h:
            scale = min(1.0, IMAGE_MAX / max(w, h))
            return round(w * scale), round(h * scale)
    return None, None


def normalize(row: dict[str, Any]) -> list[StockResult]:
    """Every CC0 image of an object (an object may have several)."""
    content = row.get("content") or {}
    dnr = content.get("descriptiveNonRepeating") or {}
    freetext = content.get("freetext") or {}
    media = ((dnr.get("online_media") or {}).get("media")) or []
    title = clean(row.get("title") or (dnr.get("title") or {}).get("content"), 300)
    creator = _first(freetext.get("name"))
    provider = clean(dnr.get("data_source"), 80) or "Smithsonian"
    landing = https(dnr.get("record_link")) or https(dnr.get("guid"))
    out = []
    for m in media:
        if not isinstance(m, dict) or m.get("type") != "Images" or not m.get("idsId"):
            continue
        if ((m.get("usage") or {}).get("access") or "").upper() != "CC0":
            continue
        ids = quote(str(m["idsId"]), safe="")
        width, height = _size(m)
        result = StockResult(
            source=NAME, source_id=f"{row.get('id')}|{m['idsId']}", title=title, creator=creator,
            license="cc0", license_version="1.0", license_url="https://creativecommons.org/publicdomain/zero/1.0/",
            provider_label=provider, landing_url=landing,
            image_url=f"{DELIVERY}?id={ids}&max={IMAGE_MAX}", thumb_url=f"{DELIVERY}?id={ids}&max={THUMB_MAX}",
            width=width, height=height,
        )
        result.credit_line = credit_line(result)
        out.append(result)
    return out


async def search(query: str, page: int) -> list[StockResult]:
    data = await get_json(f"{API}/search", {
        "q": f"({query}) AND online_visual_material:true", "rows": PAGE_SIZE, "start": page * PAGE_SIZE,
        "api_key": _key(),
    })
    rows = ((data or {}).get("response") or {}).get("rows") or []
    return [r for row in rows if isinstance(row, dict) for r in normalize(row)]


async def resolve(source_id: str) -> Optional[StockResult]:
    record_id, _, ids_id = source_id.partition("|")
    if not record_id or not ids_id:
        return None
    data = await get_json(f"{API}/content/{quote(record_id, safe='')}", {"api_key": _key()})
    row = (data or {}).get("response")
    if not isinstance(row, dict):
        return None
    return next((r for r in normalize(row) if r.source_id == source_id), None)
