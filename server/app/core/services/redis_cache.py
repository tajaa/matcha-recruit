"""Lightweight Redis cache module for server-side response caching."""

import json
from typing import Any, Optional

import redis.asyncio as aioredis

_redis_client: Optional[aioredis.Redis] = None


async def init_redis_cache(redis_url: str) -> None:
    global _redis_client
    _redis_client = aioredis.from_url(redis_url, decode_responses=True)
    print("[Cache] Redis cache connected")


async def close_redis_cache() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


def get_redis_cache() -> Optional[aioredis.Redis]:
    return _redis_client


async def cache_get(redis: aioredis.Redis, key: str) -> Optional[Any]:
    try:
        raw = await redis.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception:
        return None


async def cache_set(redis: aioredis.Redis, key: str, value: Any, ttl: int = 300) -> None:
    try:
        await redis.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        pass


async def cache_delete(redis: aioredis.Redis, key: str) -> None:
    try:
        await redis.delete(key)
    except Exception:
        pass


# --- Key builders (add more as other pages adopt caching) ---
def offer_letters_key(company_id) -> str:
    return f"offer_letters:{company_id}"
