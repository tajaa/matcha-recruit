"""Pure and fake-connection coverage for shoutout offer lifecycle invariants."""
import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.tellus.models.promo import CampaignCreate
from app.tellus.models.shoutouts import ShoutoutApproveIn
from app.tellus.services.shoutout import offers_service


def test_shoutout_is_response_only_for_generic_campaign_creation():
    with pytest.raises(ValueError):
        CampaignCreate(title="Hidden", reward_text="Thanks", max_claims=1, campaign_type="shoutout")


def test_approve_request_supports_per_offer_overrides():
    assert {"store_id", "title", "terms", "expiry_days"}.issubset(ShoutoutApproveIn.model_fields)


def test_mint_offer_is_transaction_owned_and_idempotent():
    source = inspect.getsource(offers_service.mint_offer)
    assert "client_request_id" in source
    assert "WHERE o.brand_id = $1 AND o.client_request_id = $2" in source
    assert "conn.transaction" not in source


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _ClaimConn:
    def __init__(self, offer, existing_card=None):
        self.offer = offer
        self.existing_card = existing_card
        self.calls = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if "FROM tellus_shoutout_offers" in query:
            return self.offer
        if "FROM tellus_promo_cards" in query:
            return self.existing_card
        raise AssertionError(f"Unexpected query: {query}")

    async def fetchval(self, query, *_):
        if "FROM tellus_accounts" in query:
            return False
        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query, *_):
        assert "UPDATE tellus_shoutout_offers" in query


def _offer(**overrides):
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(), "campaign_id": uuid4(), "claim_token": "claim", "reward_text": "Coffee",
        "store_name": "Main", "status": "sent", "campaign_status": "active", "starts_at": None,
        "ends_at": now + timedelta(days=1), "claim_count": 0, "max_claims": 1, "plan_status": "active",
        "claim_expires_at": now + timedelta(days=1), "offer_created_at": now, "require_app_install": False,
        "brand_name": "Cafe", "brand_logo_url": None, "offer_terms": None, "short_code": "ABCDEFGH",
    } | overrides


def test_code_preview_uses_short_code_identifier():
    conn = _ClaimConn(_offer())

    preview = asyncio.run(offers_service.preview_offer(conn, short_code="ABCDEFGH", account_id=None))

    assert preview["short_code"] == "ABCDEFGH"
    assert conn.calls[0][1][-2:] == (None, "ABCDEFGH")


def test_claim_replay_returns_existing_card_before_cap_check(monkeypatch):
    conn = _ClaimConn(_offer(claim_count=1, status="claimed"), existing_card={"card_token": "card"})

    async def claim_card(*_):
        return {"card_token": "card"}, False

    monkeypatch.setattr(offers_service.promo_service, "claim_card", claim_card)
    result = asyncio.run(offers_service.claim_offer(conn, token="offer", account_id=uuid4()))

    assert result["card_token"] == "card"
    assert result["created"] is False


def test_install_gate_blocks_new_web_accounts_but_not_ios(monkeypatch):
    conn = _ClaimConn(_offer(require_app_install=True))
    account_id = uuid4()

    with pytest.raises(offers_service.OfferError, match="Install the Tell-Us"):
        asyncio.run(offers_service.claim_offer(conn, token="offer", account_id=account_id))

    async def claim_card(*_):
        return {"card_token": "card"}, True

    monkeypatch.setattr(offers_service.promo_service, "claim_card", claim_card)
    result = asyncio.run(offers_service.claim_offer(conn, token="offer", account_id=account_id, client_kind="ios"))
    assert result["created"] is True
