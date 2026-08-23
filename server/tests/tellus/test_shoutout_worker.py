"""Behavioral coverage for the pool-free Tell-Us scan dispatcher."""
import asyncio

from app.workers import celery_app
from app.workers.tasks import tellus_shoutout_scan


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _Conn:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.closed = False

    async def fetchrow(self, query, *_):
        if "UPDATE scheduler_settings" in query:
            return {"max_per_cycle": 10}
        raise AssertionError(f"Unexpected query: {query}")

    async def fetch(self, query, *_):
        assert "FROM tellus_shoutout_configs" in query
        return self.rows

    async def close(self):
        self.closed = True

    def transaction(self):
        return _Transaction()


def test_task_is_registered_and_has_no_retries():
    assert "app.workers.tasks.tellus_shoutout_scan" in celery_app.celery_app.conf.include
    task = tellus_shoutout_scan.run_tellus_shoutout_scan
    assert task.max_retries == 0
    assert ("tellus_shoutout_scan", "app.workers.tasks.tellus_shoutout_scan", "run_tellus_shoutout_scan") in celery_app._SCHEDULED_TASKS


def test_dispatcher_continues_after_one_brand_failure(monkeypatch):
    first = _Conn(rows=[{"brand_id": "good-one"}, {"brand_id": "bad"}, {"brand_id": "good-two"}])
    connections = [first, _Conn(), _Conn(), _Conn()]
    scanned = []

    async def get_connection():
        return connections.pop(0)

    async def enabled(*_, **kwargs):
        assert kwargs["default"] is False
        return True

    async def scan_brand(_conn, brand_id):
        scanned.append(brand_id)
        if brand_id == "bad":
            raise RuntimeError("provider failed")

    monkeypatch.setattr(tellus_shoutout_scan, "get_db_connection", get_connection)
    monkeypatch.setattr(tellus_shoutout_scan, "scheduler_enabled", enabled)
    monkeypatch.setattr(tellus_shoutout_scan, "scan_brand", scan_brand)

    result = asyncio.run(tellus_shoutout_scan._dispatch())

    assert result == {"status": "completed", "scanned": 2, "failed": 1}
    assert scanned == ["good-one", "bad", "good-two"]
    assert first.closed


def test_dispatcher_defaults_closed_without_brand_queries(monkeypatch):
    conn = _Conn()

    async def get_connection():
        return conn

    async def disabled(*_, **kwargs):
        assert kwargs["default"] is False
        return False

    monkeypatch.setattr(tellus_shoutout_scan, "get_db_connection", get_connection)
    monkeypatch.setattr(tellus_shoutout_scan, "scheduler_enabled", disabled)

    assert asyncio.run(tellus_shoutout_scan._dispatch()) == {"status": "disabled", "scanned": 0}
    assert conn.closed
