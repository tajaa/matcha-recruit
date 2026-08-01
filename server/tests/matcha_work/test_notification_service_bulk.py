"""create_notifications_bulk degrades to per-member inserts when the single
batched INSERT fails (e.g. one recipient's company_id doesn't resolve against
the companies table — both FK columns on mw_notifications are NOT NULL, so a
multi-row INSERT...SELECT FROM unnest(...) fails as one statement).

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_notification_service_bulk.py -q
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services import notification_service as notif_svc


class _FakeConn:
    def __init__(self, fetch_should_raise: bool):
        self._fetch_should_raise = fetch_should_raise
        self.fetchrow_calls = []

    async def fetch(self, *args, **kwargs):
        if self._fetch_should_raise:
            raise RuntimeError("insert or update on table \"mw_notifications\" violates foreign key constraint")
        return []

    async def fetchrow(self, *args, **kwargs):
        # args[1] is user_id, args[2] is company_id per create_notification's
        # positional bind order (user_id, company_id, type, title, body, link, metadata_json).
        user_id = args[1]
        self.fetchrow_calls.append(user_id)
        return {
            "id": uuid4(), "user_id": user_id, "company_id": args[2], "type": args[3],
            "title": args[4], "body": args[5], "link": args[6], "metadata": {},
            "is_read": False, "created_at": None,
        }


def _patch_get_connection(monkeypatch, conn: _FakeConn):
    @asynccontextmanager
    async def _fake_get_connection():
        yield conn
    # notification_service.py does `from ...database import get_connection` —
    # patch the name as imported into THIS module, not the defining one.
    monkeypatch.setattr(notif_svc, "get_connection", _fake_get_connection)


@pytest.mark.asyncio
async def test_bulk_insert_success_does_not_fall_back(monkeypatch):
    conn = _FakeConn(fetch_should_raise=False)
    _patch_get_connection(monkeypatch, conn)
    monkeypatch.setattr(notif_svc, "create_notification", AsyncMock())

    user_ids = [uuid4(), uuid4()]
    company_ids = [uuid4(), uuid4()]
    await notif_svc.create_notifications_bulk(
        user_ids=user_ids, company_ids=company_ids, type="channel_message", title="#general", body="hi",
    )
    notif_svc.create_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_insert_failure_falls_back_to_every_member(monkeypatch):
    # The bug this closes: one member with a dangling company_id/org_id
    # failed the whole batched INSERT, so a 200-member channel got ZERO
    # bells for a message instead of 199. The fallback must still reach
    # every recipient, not just skip the batch.
    conn = _FakeConn(fetch_should_raise=True)
    _patch_get_connection(monkeypatch, conn)

    user_ids = [uuid4(), uuid4(), uuid4()]
    company_ids = [uuid4(), uuid4(), uuid4()]
    await notif_svc.create_notifications_bulk(
        user_ids=user_ids, company_ids=company_ids, type="channel_message", title="#general", body="hi",
    )
    assert conn.fetchrow_calls == user_ids


@pytest.mark.asyncio
async def test_bulk_insert_failure_one_bad_member_does_not_block_the_rest(monkeypatch):
    conn = _FakeConn(fetch_should_raise=True)
    _patch_get_connection(monkeypatch, conn)
    good_ids = [uuid4(), uuid4()]
    bad_id = uuid4()
    user_ids = [good_ids[0], bad_id, good_ids[1]]
    company_ids = [uuid4(), uuid4(), uuid4()]

    real_fetchrow = conn.fetchrow

    async def _flaky_fetchrow(*args, **kwargs):
        if args[1] == bad_id:
            raise RuntimeError("still broken for this one")
        return await real_fetchrow(*args, **kwargs)
    conn.fetchrow = _flaky_fetchrow

    await notif_svc.create_notifications_bulk(
        user_ids=user_ids, company_ids=company_ids, type="channel_message", title="#general", body="hi",
    )
    assert conn.fetchrow_calls == good_ids
