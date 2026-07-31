"""Unit tests for `get_rate_limit_state` — the read-only peek at a
`check_rate_limit` redis counter, used by GET /matcha-work/usage/meter.
No real redis: a FakeRedis stub scripts `.get`/`.ttl`.

    cd server && ./venv/bin/python -m pytest tests/core/test_rate_limit_state.py -q
"""

import asyncio

from app.core.services import redis_cache


def _run(coro):
    return asyncio.run(coro)


class FakeRedis:
    def __init__(self, *, value=None, ttl=-2, raise_on_get=False):
        self.value = value
        self.ttl_value = ttl
        self.raise_on_get = raise_on_get
        self.get_calls: list[str] = []

    async def get(self, key):
        self.get_calls.append(key)
        if self.raise_on_get:
            raise ConnectionError("redis down")
        return self.value

    async def ttl(self, key):
        return self.ttl_value


class TestGetRateLimitState:
    def test_no_redis_returns_none(self, monkeypatch):
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: None)
        result = _run(redis_cache.get_rate_limit_state("company-1", "huume_turn", 120, 3600))
        assert result is None

    def test_missing_key_reads_zero(self, monkeypatch):
        fake = FakeRedis(value=None, ttl=-2)
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        result = _run(redis_cache.get_rate_limit_state("company-1", "huume_turn", 120, 3600))
        assert result == {"used": 0, "limit": 120, "remaining": 120, "resets_in_seconds": 0}

    def test_no_expiry_ttl_collapses_to_zero(self, monkeypatch):
        fake = FakeRedis(value="3", ttl=-1)
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        result = _run(redis_cache.get_rate_limit_state("company-1", "huume_turn", 120, 3600))
        assert result["resets_in_seconds"] == 0

    def test_counts_and_ttl(self, monkeypatch):
        fake = FakeRedis(value="7", ttl=1800)
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        result = _run(redis_cache.get_rate_limit_state("company-1", "huume_turn", 120, 3600))
        assert result == {"used": 7, "limit": 120, "remaining": 113, "resets_in_seconds": 1800}

    def test_over_limit_clamps_remaining(self, monkeypatch):
        fake = FakeRedis(value="140", ttl=900)
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        result = _run(redis_cache.get_rate_limit_state("company-1", "huume_turn", 120, 3600))
        assert result["used"] == 140
        assert result["remaining"] == 0

    def test_redis_error_returns_none(self, monkeypatch):
        fake = FakeRedis(raise_on_get=True)
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        result = _run(redis_cache.get_rate_limit_state("company-1", "huume_turn", 120, 3600))
        assert result is None

    def test_key_shape_matches_check_rate_limit(self, monkeypatch):
        # get_rate_limit_state must read the exact key check_rate_limit
        # writes (rl:{action}:{key}) or the meter silently reads nothing.
        fake = FakeRedis(value="1", ttl=100)
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        _run(redis_cache.get_rate_limit_state("abc-123", "huume_turn", 120, 3600))
        assert fake.get_calls == ["rl:huume_turn:abc-123"]
