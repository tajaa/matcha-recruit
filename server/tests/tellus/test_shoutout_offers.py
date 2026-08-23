"""Pure/source guards for shoutout offer lifecycle invariants."""
import inspect

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
