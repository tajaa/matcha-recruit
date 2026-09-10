"""Per-provider rate-limit buckets.

    cd server && ./venv/bin/python -m pytest tests/core/test_rate_limiter_buckets.py -q

The bug these pin: `check_limit` counted every row in `api_rate_limits` with no
filter and compared the total against the Gemini ceiling. Once the Huume and
Espresso loops moved to OpenAI (2026-08-25) while still recording here, OpenAI
traffic spent the Gemini allowance and a Gemini-heavy compliance sweep could
429 a Huume turn.

No database: the connection is a fake that records the SQL and its arguments,
which is the whole surface under test — what we count, and what we count it
against.
"""

import asyncio
from types import SimpleNamespace
from unittest import mock

import pytest

from app.core.services import rate_limiter as rl


def _run(coro):
    return asyncio.run(coro)


class _FakeConn:
    def __init__(self, counts=(0, 0)):
        self.counts = list(counts)
        self.queries: list[tuple[str, tuple]] = []
        self.inserts: list[tuple] = []

    async def fetchval(self, query, *args):
        self.queries.append((" ".join(query.split()), args))
        return self.counts.pop(0) if self.counts else 0

    async def fetch(self, query, *args):
        self.queries.append((" ".join(query.split()), args))
        return []

    async def execute(self, query, *args):
        self.inserts.append((" ".join(query.split()), args))


def _patch(monkeypatch, conn, **limits):
    settings = SimpleNamespace(
        gemini_hourly_limit=limits.get("gemini_hourly", 200),
        gemini_daily_limit=limits.get("gemini_daily", 5000),
        openai_hourly_limit=limits.get("openai_hourly", 200),
        openai_daily_limit=limits.get("openai_daily", 5000),
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)

    class Ctx:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(rl, "get_connection", lambda *a, **k: Ctx())


def test_each_provider_counts_only_its_own_rows(monkeypatch):
    conn = _FakeConn()
    _patch(monkeypatch, conn)

    _run(rl.ApiRateLimiter(provider="openai").check_limit("huume", "agent"))

    assert len(conn.queries) == 2
    for query, args in conn.queries:
        # The filter is the entire point — without it one provider's traffic
        # is counted against the other's ceiling.
        assert "provider = $2" in query, query
        assert args[1] == "openai"


def test_the_default_bucket_is_gemini_so_existing_callers_are_unchanged(monkeypatch):
    conn = _FakeConn()
    _patch(monkeypatch, conn)

    limiter = rl.ApiRateLimiter()
    assert limiter.provider == "gemini"
    _run(limiter.check_limit("gemini_compliance", "scan"))
    assert all(args[1] == "gemini" for _q, args in conn.queries)


def test_each_provider_gets_its_own_ceiling(monkeypatch):
    conn = _FakeConn()
    _patch(monkeypatch, conn, gemini_hourly=200, gemini_daily=5000,
           openai_hourly=40, openai_daily=900)

    assert rl.ApiRateLimiter().hourly_limit == 200
    assert rl.ApiRateLimiter().daily_limit == 5000
    assert rl.ApiRateLimiter(provider="openai").hourly_limit == 40
    assert rl.ApiRateLimiter(provider="openai").daily_limit == 900


def test_a_gemini_flood_does_not_block_an_openai_turn(monkeypatch):
    """The reported failure mode, end to end: a Gemini-heavy sweep has filled
    the hour, and a Huume turn must still be allowed through."""
    # The OpenAI bucket's own counts are what its query returns — the Gemini
    # rows are simply not in it.
    conn = _FakeConn(counts=(0, 0))
    _patch(monkeypatch, conn, openai_hourly=10)
    _run(rl.ApiRateLimiter(provider="openai").check_limit("huume", "agent"))  # no raise

    # ...and the same flood still blocks Gemini, which is the limiter working.
    conn = _FakeConn(counts=(200, 200))
    _patch(monkeypatch, conn, gemini_hourly=200)
    with pytest.raises(rl.RateLimitExceeded) as excinfo:
        _run(rl.ApiRateLimiter().check_limit("gemini_compliance", "scan"))
    assert excinfo.value.limit_type == "hourly"
    assert "gemini" in str(excinfo.value)


def test_a_recorded_call_is_stamped_with_its_provider(monkeypatch):
    conn = _FakeConn()
    _patch(monkeypatch, conn)

    _run(rl.ApiRateLimiter(provider="openai").record_call("huume", "agent"))

    query, args = conn.inserts[0]
    assert "provider" in query
    assert args[0] == "huume" and args[3] == "openai"


def test_usage_stats_are_scoped_to_the_bucket_they_report_limits_for(monkeypatch):
    """The admin page shows a count next to a limit. Counting every provider
    while showing one provider's ceiling is how a bucket looks full when it
    isn't."""
    conn = _FakeConn(counts=(3, 9, None))
    _patch(monkeypatch, conn)

    usage = _run(rl.ApiRateLimiter(provider="openai").get_usage())

    assert usage["provider"] == "openai"
    assert all(
        "provider = $" in query
        for query, _args in conn.queries
        if "api_rate_limits" in query
    )


def test_the_singleton_is_per_provider(monkeypatch):
    conn = _FakeConn()
    _patch(monkeypatch, conn)
    monkeypatch.setattr(rl, "_rate_limiters", {})

    gemini, openai = rl.get_rate_limiter(), rl.get_rate_limiter("openai")
    assert gemini is not openai
    assert gemini is rl.get_rate_limiter()
    assert openai.provider == "openai"


def test_every_construction_site_in_the_app_picks_a_real_bucket():
    """A typo'd provider would silently get its own empty bucket and never
    limit anything, which is worse than the bug this replaced."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    used = set()
    for path in root.rglob("*.py"):
        for match in re.finditer(r'ApiRateLimiter\(\s*(?:provider\s*=\s*)?"([a-z]+)"', path.read_text()):
            used.add(match.group(1))
    assert used <= {"gemini", "openai"}, used
