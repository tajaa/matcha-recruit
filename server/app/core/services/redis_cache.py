"""Lightweight Redis cache module for server-side response caching."""

import json
import os
import time as _time
from collections import defaultdict
from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, Request

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

def jurisdictions_key() -> str:
    return "jurisdictions"

def dashboard_stats_key(company_id) -> str:
    return f"dashboard_stats:{company_id}"

def dashboard_upcoming_key(company_id, days) -> str:
    return f"dashboard_upcoming:{company_id}:{days}"

def dashboard_credentials_key(company_id) -> str:
    return f"dashboard_credentials:{company_id}"

def dashboard_notifications_key(company_id, limit, offset) -> str:
    return f"dashboard_notifications:{company_id}:{limit}:{offset}"

def compliance_dashboard_key(company_id, horizon_days) -> str:
    return f"compliance_dashboard:{company_id}:{horizon_days}"

def pinned_requirements_key(company_id) -> str:
    return f"pinned_requirements:{company_id}"

def admin_jurisdictions_list_key() -> str:
    return "admin_jurisdictions_list"

def admin_jurisdiction_detail_key(jurisdiction_id) -> str:
    return f"admin_jurisdiction_detail:{jurisdiction_id}"

def admin_jurisdiction_data_overview_key() -> str:
    return "admin_jurisdiction_data_overview"

def admin_jurisdiction_policy_overview_key(category=None) -> str:
    return f"admin_jurisdiction_policy_overview:{category or '_all'}"

def admin_bookmarked_requirements_key() -> str:
    return "admin_bookmarked_requirements"


_rl_attempts: dict[str, list[float]] = defaultdict(list)


_TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "1"))


def client_ip(request: Request) -> str:
    """Real client IP, proxy-aware (anti-spoofing for rate limits).

    nginx appends to X-Forwarded-For via `$proxy_add_x_forwarded_for`, so the
    RIGHTMOST entries are set by our own trusted proxies and the LEFTMOST are
    client-supplied and spoofable. Taking the leftmost (the old behaviour) let an
    attacker rotate `X-Forwarded-For` per request and defeat every IP rate limit.
    We take the entry just left of our trusted proxies (default 1 = single nginx
    hop; override with TRUSTED_PROXY_COUNT if more proxies sit in front).
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            idx = max(0, len(parts) - _TRUSTED_PROXY_COUNT)
            return parts[idx]
    return request.client.host if request.client else "unknown"


async def check_rate_limit(ip: str, action: str, limit: int, window: int) -> None:
    """Raise 429 if ip exceeds limit requests for action within window seconds."""
    redis = get_redis_cache()
    if redis:
        key = f"rl:{action}:{ip}"
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window)
            if count > limit:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(window)},
                )
            return
        except HTTPException:
            raise
        except Exception:
            pass
    fk = f"{action}:{ip}"
    now = _time.monotonic()
    _rl_attempts[fk] = [t for t in _rl_attempts[fk] if t > now - window]
    if len(_rl_attempts[fk]) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(window)},
        )
    _rl_attempts[fk].append(now)


async def cache_delete_pattern(redis, prefix: str) -> None:
    """Delete all keys matching a prefix. Use sparingly."""
    try:
        cursor = b"0"
        while cursor:
            cursor, keys = await redis.scan(cursor=cursor, match=f"{prefix}*", count=100)
            if keys:
                await redis.delete(*keys)
    except Exception:
        pass
