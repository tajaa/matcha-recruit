"""`refund_rate_limit` — giving back one `check_rate_limit` charge for a call
that failed on our side (a model that was down), so it doesn't use up the
person's day. A FakeRedis stands in for the counter; no real redis.

    cd server && ./venv/bin/python -m pytest tests/core/test_rate_limit_refund.py -q
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.core.services import redis_cache


def _run(coro):
    return asyncio.run(coro)


class FakeRedis:
    """A counter per key, with the four calls `check_rate_limit` and the refund make."""

    def __init__(self, counts=None, *, broken=False):
        self.counts = dict(counts or {})
        self.expiring: dict[str, int] = {}
        self.broken = broken

    def _up(self):
        if self.broken:
            raise ConnectionError("redis down")

    async def incr(self, key):
        self._up()
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def decr(self, key):
        self._up()
        self.counts[key] = self.counts.get(key, 0) - 1
        return self.counts[key]

    async def delete(self, key):
        self._up()
        self.counts.pop(key, None)

    async def expire(self, key, seconds):
        self._up()
        self.expiring[key] = seconds


@pytest.fixture(autouse=True)
def _clean_fallback():
    redis_cache._rl_attempts.clear()
    yield
    redis_cache._rl_attempts.clear()


class TestWithRedis:
    def test_gives_back_one_charge_on_the_key_check_rate_limit_writes(self, monkeypatch):
        fake = FakeRedis()
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        for _ in range(3):
            _run(redis_cache.check_rate_limit("acct", "merlin", 9, 86_400))
        assert fake.counts == {"rl:merlin:acct": 3}
        _run(redis_cache.refund_rate_limit("acct", "merlin"))
        assert fake.counts == {"rl:merlin:acct": 2}

    def test_a_refunded_day_can_be_used_to_the_limit(self, monkeypatch):
        fake = FakeRedis()
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        for _ in range(2):
            _run(redis_cache.check_rate_limit("acct", "merlin", 2, 60))
        with pytest.raises(HTTPException) as over:
            _run(redis_cache.check_rate_limit("acct", "merlin", 2, 60))
        assert over.value.status_code == 429
        # That third attempt was counted too; two refunds bring the day back to one used.
        _run(redis_cache.refund_rate_limit("acct", "merlin"))
        _run(redis_cache.refund_rate_limit("acct", "merlin"))
        _run(redis_cache.check_rate_limit("acct", "merlin", 2, 60))

    def test_the_last_charge_removes_the_key_so_the_window_starts_fresh(self, monkeypatch):
        fake = FakeRedis({"rl:merlin:acct": 1})
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        _run(redis_cache.refund_rate_limit("acct", "merlin"))
        assert fake.counts == {}

    def test_a_key_that_was_never_there_is_not_left_negative(self, monkeypatch):
        fake = FakeRedis()
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        _run(redis_cache.refund_rate_limit("acct", "merlin"))
        assert fake.counts == {}

    def test_only_that_person_and_action_are_touched(self, monkeypatch):
        fake = FakeRedis({"rl:merlin:acct": 2, "rl:merlin:other": 5, "rl:ask:acct": 4})
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: fake)
        _run(redis_cache.refund_rate_limit("acct", "merlin"))
        assert fake.counts == {"rl:merlin:acct": 1, "rl:merlin:other": 5, "rl:ask:acct": 4}

    def test_a_broken_redis_never_raises(self, monkeypatch):
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: FakeRedis(broken=True))
        _run(redis_cache.refund_rate_limit("acct", "merlin"))


class TestWithoutRedis:
    def test_takes_back_the_last_attempt_of_the_in_process_fallback(self, monkeypatch):
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: None)
        for _ in range(2):
            _run(redis_cache.check_rate_limit("acct", "merlin", 2, 60))
        with pytest.raises(HTTPException):
            _run(redis_cache.check_rate_limit("acct", "merlin", 2, 60))
        _run(redis_cache.refund_rate_limit("acct", "merlin"))
        _run(redis_cache.check_rate_limit("acct", "merlin", 2, 60))

    def test_nothing_to_give_back_is_fine(self, monkeypatch):
        monkeypatch.setattr(redis_cache, "get_redis_cache", lambda: None)
        _run(redis_cache.refund_rate_limit("acct", "merlin"))
        assert not redis_cache._rl_attempts.get("merlin:acct")
