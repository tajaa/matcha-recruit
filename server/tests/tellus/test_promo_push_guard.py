"""push_campaign must not burn its one-shot push when zero devices match —
the already_pushed guard makes a stamped push_sent_at permanent, so a
zero-recipient send would make the campaign unretryable forever.
No real DB — a hand-written fake connection records executed SQL so the
test can assert the push_sent_at UPDATE ran (or didn't) without a live
Postgres connection.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.tellus.services import promo_service, push as push_service

NOW = datetime.now(timezone.utc)
BRAND_ID = uuid4()
CAMPAIGN_ID = uuid4()


def _campaign_row(**overrides):
    row = {
        "id": CAMPAIGN_ID,
        "brand_id": BRAND_ID,
        "campaign_type": "location",
        "push_sent_at": None,
        "status": "active",
        "plan_status": "active",
        "starts_at": None,
        "ends_at": None,
        "radius_miles": 2.0,
        "store_lat": 37.0,
        "store_lng": -122.0,
        "store_name": "Main St",
        "brand_name": "Acme",
        "brand_slug": "acme",
        "claim_token": "tok123",
        "title": "Fall Sale",
        "description": "20% off",
    }
    row.update(overrides)
    return row


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    """campaign_row: the SELECT ... FOR UPDATE OF c result.
    device_rows: the SELECT DISTINCT ON (dt.token) ... result."""

    def __init__(self, campaign_row, device_rows):
        self.campaign_row = campaign_row
        self.device_rows = device_rows
        self.executed: list[str] = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        return self.campaign_row

    async def fetch(self, query, *args):
        return self.device_rows

    async def execute(self, query, *args):
        self.executed.append(query)
        return "OK"


def _device_row(token: str, account_id):
    return {"token": token, "account_id": account_id}


@pytest.mark.asyncio
async def test_zero_recipients_does_not_stamp_push_sent_at():
    conn = _Connection(_campaign_row(), device_rows=[])

    result = await promo_service.push_campaign(conn, BRAND_ID, CAMPAIGN_ID)

    assert result == {
        "sent_count": 0,
        "pushed": False,
        "store_name": "Main St",
        "radius_miles": 2.0,
    }
    assert not any("push_sent_at" in q for q in conn.executed)
    assert not any("tellus_notifications" in q for q in conn.executed)


@pytest.mark.asyncio
async def test_recipients_stamp_push_sent_at(monkeypatch):
    monkeypatch.setattr(push_service, "schedule_token_push", lambda *a, **k: None)
    acct_a, acct_b = uuid4(), uuid4()
    rows = [_device_row("tok-a", acct_a), _device_row("tok-b", acct_b)]
    conn = _Connection(_campaign_row(), device_rows=rows)

    result = await promo_service.push_campaign(conn, BRAND_ID, CAMPAIGN_ID)

    assert result["sent_count"] == 2
    assert result["pushed"] is True
    assert any("tellus_notifications" in q for q in conn.executed)
    assert any("push_sent_at" in q for q in conn.executed)


@pytest.mark.asyncio
async def test_duplicate_account_ids_dedupe_to_one_recipient(monkeypatch):
    monkeypatch.setattr(push_service, "schedule_token_push", lambda *a, **k: None)
    acct = uuid4()
    rows = [_device_row("tok-a", acct), _device_row("tok-b", acct)]
    conn = _Connection(_campaign_row(), device_rows=rows)

    result = await promo_service.push_campaign(conn, BRAND_ID, CAMPAIGN_ID)

    assert result["sent_count"] == 1
    assert result["pushed"] is True
