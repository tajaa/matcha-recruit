"""notify_campaign_followers must not push a "just started" alert for a
campaign whose starts_at is still in the future — the 2026-08-14 code review
caught it firing immediately regardless of a future start date, landing
followers on a campaign claim_reason() itself reports as "not_started".
No DB — conn is an AsyncMock; the guard must return before any query runs.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.tellus.services import promo_service


@pytest.mark.asyncio
async def test_future_starts_at_skips_notification_entirely():
    conn = AsyncMock()
    campaign = {"title": "Fall Sale", "starts_at": datetime.now(timezone.utc) + timedelta(days=1)}

    await promo_service.notify_campaign_followers(conn, uuid4(), campaign)

    conn.fetchrow.assert_not_called()
    conn.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_none_starts_at_proceeds_past_the_guard():
    conn = AsyncMock()
    conn.fetchrow.return_value = None  # brand lookup misses -> early-returns right after
    campaign = {"title": "Fall Sale", "starts_at": None}

    await promo_service.notify_campaign_followers(conn, uuid4(), campaign)

    conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_past_starts_at_proceeds_past_the_guard():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    campaign = {"title": "Fall Sale", "starts_at": datetime.now(timezone.utc) - timedelta(days=1)}

    await promo_service.notify_campaign_followers(conn, uuid4(), campaign)

    conn.fetchrow.assert_called_once()
