"""Expired mobile sessions are removed in bounded, migration-safe batches."""

from types import SimpleNamespace

import pytest

from app.workers.celery_app import celery_app
from app.workers.tasks import auth_device_sessions


class _Connection:
    def __init__(self, table_exists=True):
        self.table_exists = table_exists
        self.executed = None
        self.closed = False

    async def fetchval(self, query):
        assert "to_regclass('auth_device_sessions')" in query
        return "auth_device_sessions" if self.table_exists else None

    async def execute(self, query, *args):
        self.executed = (query, args)
        return "DELETE 3"

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_cleanup_uses_absolute_lifetime_and_bounded_oldest_batch(monkeypatch):
    conn = _Connection()

    async def connection():
        return conn

    monkeypatch.setattr(auth_device_sessions, "get_db_connection", connection)
    monkeypatch.setattr(auth_device_sessions, "get_settings", lambda: SimpleNamespace(
        jwt_session_absolute_expire_hours=12,
    ))

    assert await auth_device_sessions._prune_device_sessions() == {"skipped": False, "deleted": 3}
    query, args = conn.executed
    assert args == (2, 1000)
    assert "ORDER BY created_at" in query
    assert "FOR UPDATE SKIP LOCKED" in query
    assert conn.closed


@pytest.mark.asyncio
async def test_cleanup_skips_before_device_session_migration(monkeypatch):
    conn = _Connection(table_exists=False)

    async def connection():
        return conn

    monkeypatch.setattr(auth_device_sessions, "get_db_connection", connection)
    monkeypatch.setattr(auth_device_sessions, "get_settings", lambda: SimpleNamespace(
        jwt_session_absolute_expire_hours=12,
    ))

    assert await auth_device_sessions._prune_device_sessions() == {"skipped": True, "deleted": 0}
    assert conn.executed is None
    assert conn.closed


def test_cleanup_is_registered_before_worker_ready_dispatch():
    assert "app.workers.tasks.auth_device_sessions" in celery_app.conf.include
    celery_app.loader.import_default_modules()
    assert "auth.prune_device_sessions" in celery_app.tasks
