"""`run_with_chat_fanout`: a worker task's chat posts reach open chats live.

The socket fanout publishes on the shared Redis client, which only the API
opens. A task must open one on its own event loop (asyncio clients are bound
to the loop they connect on) and close it after.
"""
from app.core.services import redis_cache
from app.workers import utils


def test_opens_a_client_for_the_task_and_closes_it_after(monkeypatch):
    monkeypatch.setattr(redis_cache, "_redis_client", None)
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # lazy: never dialled here

    async def task():
        return redis_cache.get_redis_cache()

    assert utils.run_with_chat_fanout(task()) is not None
    assert redis_cache.get_redis_cache() is None


def test_reuses_a_client_that_is_already_open(monkeypatch):
    existing = object()
    monkeypatch.setattr(redis_cache, "_redis_client", existing)

    async def task():
        return redis_cache.get_redis_cache()

    assert utils.run_with_chat_fanout(task()) is existing
    assert redis_cache.get_redis_cache() is existing  # not closed: not ours


def test_the_task_still_runs_when_redis_cannot_open(monkeypatch):
    monkeypatch.setattr(redis_cache, "_redis_client", None)

    async def broken(url):
        raise OSError("no redis")

    monkeypatch.setattr(redis_cache, "init_redis_cache", broken)

    async def task():
        return "done"

    assert utils.run_with_chat_fanout(task()) == "done"
    assert redis_cache.get_redis_cache() is None
