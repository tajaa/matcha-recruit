"""Focused contract coverage for the paginated notification inbox."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.routes.work import notifications as routes
from app.matcha.services import notification_service as notif_svc


@pytest.mark.asyncio
async def test_notification_total_uses_the_list_scope(monkeypatch):
    user_id = uuid4()
    company_id = uuid4()

    class _Conn:
        async def fetchval(self, query, *args):
            assert "user_id = $1" in query
            assert "company_id = $2" in query
            assert "is_read = FALSE" in query
            assert args == (user_id, company_id)
            return 61

    @asynccontextmanager
    async def fake_connection():
        yield _Conn()

    monkeypatch.setattr(notif_svc, "get_connection", fake_connection)

    assert await notif_svc.count_notifications(
        user_id, company_id=company_id, unread_only=True,
    ) == 61


@pytest.mark.asyncio
async def test_list_notifications_returns_filtered_total(monkeypatch):
    user_id = uuid4()
    company_id = uuid4()
    notification_id = uuid4()
    row = {
        "id": notification_id,
        "type": "schedule_request_pending",
        "title": "Shift swap request awaiting approval",
        "body": "Review it.",
        "link": "/ops/schedule?tab=requests",
        "metadata": {"request_id": str(uuid4())},
        "is_read": False,
        "created_at": datetime(2026, 8, 28, tzinfo=timezone.utc),
    }

    async def fake_company(_current_user):
        return company_id

    async def fake_list(*args, **kwargs):
        assert args == (user_id,)
        assert kwargs == {
            "company_id": company_id,
            "unread_only": True,
            "limit": 30,
            "offset": 30,
        }
        return [row]

    async def fake_count(*args, **kwargs):
        assert args == (user_id,)
        assert kwargs == {"company_id": company_id, "unread_only": True}
        return 61

    monkeypatch.setattr(routes, "get_client_company_id", fake_company)
    monkeypatch.setattr(routes.notif_svc, "get_notifications", fake_list)
    monkeypatch.setattr(routes.notif_svc, "count_notifications", fake_count)

    result = await routes.list_notifications(
        unread_only=True,
        limit=30,
        offset=30,
        current_user=SimpleNamespace(id=user_id),
    )

    assert result["total"] == 61
    assert result["notifications"][0]["id"] == str(notification_id)
