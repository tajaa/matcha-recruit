"""Cappe public surface — archive thumbnails for the magazine Library.

`GET /public/stock-thumbs/{token}`: the token is a thumbnail URL our own
search signed (`services/magazine/sources/thumbs.py`), so this fetches only
what a search produced; it is not an open proxy. Anonymous because an `<img>`
can't carry the dashboard's bearer token — the signature is the permission.
The picture is fetched through the SSRF-guarded fetcher, re-encoded as a small
WebP and cached a day.
"""
import asyncio
import base64
import hashlib

from fastapi import Request, status
from fastapi.responses import Response

from ....core.services.redis_cache import cache_get, cache_set, check_rate_limit, client_ip, get_redis_cache
from ....core.services.safe_fetch import fetch_public
from ...services.magazine.sources import thumbs
from ._body_limit import limited_public_router

router = limited_public_router()

_CACHE_SECONDS = 86400


@router.get("/public/stock-thumbs/{token}")
async def stock_thumb(token: str, request: Request):
    await check_rate_limit(client_ip(request), "cappe_stock_thumb", 600, 600)
    url = thumbs.verify(token)
    if url is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    redis = get_redis_cache()
    # Keyed on the picture, not the token: tokens expire and are re-signed.
    key = f"cappe:stock:thumb:{hashlib.sha1(url.encode()).hexdigest()}"
    webp = None
    if redis:
        cached = await cache_get(redis, key)
        if isinstance(cached, str):
            webp = base64.b64decode(cached)
    if webp is None:
        try:
            fetched = await fetch_public(url, max_bytes=thumbs.MAX_SOURCE_BYTES, accept="image/*", total_timeout=20)
        except Exception:  # noqa: BLE001 — unsafe host, network error, timeout
            return Response(status_code=status.HTTP_502_BAD_GATEWAY)
        if fetched.status != 200 or fetched.truncated or not fetched.content_type.startswith("image/"):
            return Response(status_code=status.HTTP_502_BAD_GATEWAY)
        try:
            webp = await asyncio.to_thread(thumbs.to_webp, fetched.body)
        except Exception:  # noqa: BLE001 — not an image
            return Response(status_code=status.HTTP_502_BAD_GATEWAY)
        if redis:
            await cache_set(redis, key, base64.b64encode(webp).decode(), ttl=_CACHE_SECONDS)
    return Response(webp, media_type="image/webp",
                    headers={"Cache-Control": f"public, max-age={_CACHE_SECONDS}", "X-Content-Type-Options": "nosniff"})
