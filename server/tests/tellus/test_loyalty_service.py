"""Pure and source-guard tests for the separate loyalty economy."""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.tellus.services import loyalty_service


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeConn:
    def __init__(self):
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return None

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return None


def test_purchase_points_floor_partial_dollar():
    assert loyalty_service.points_for_purchase(199, 1, None) == 1
    assert loyalty_service.points_for_purchase(299, 2, None) == 5


def test_purchase_points_apply_event_cap():
    assert loyalty_service.points_for_purchase(100_000, 2, 1000) == 1000


def test_tier_boundaries():
    tiers = [
        {"tier_key": "bronze", "threshold_points": 0},
        {"tier_key": "silver", "threshold_points": 500},
        {"tier_key": "gold", "threshold_points": 1500},
    ]
    assert loyalty_service.tier_for_lifetime(tiers, 499) == "bronze"
    assert loyalty_service.tier_for_lifetime(tiers, 500) == "silver"
    assert loyalty_service.tier_for_lifetime(tiers, 1500) == "gold"


def test_effective_redemption_status():
    assert loyalty_service.effective_redemption_status("issued", NOW + timedelta(days=1), NOW) == "issued"
    assert loyalty_service.effective_redemption_status("issued", NOW - timedelta(seconds=1), NOW) == "expired"
    assert loyalty_service.effective_redemption_status("redeemed", NOW - timedelta(days=1), NOW) == "redeemed"


def test_member_token_types():
    assert loyalty_service.extract_member_token("TU-LM1:abc") == "abc"
    assert loyalty_service.extract_member_token("https://hey-matcha.com/tellus/member/TU-LM1:abc") == "abc"
    with pytest.raises(loyalty_service.LoyaltyError) as exc:
        loyalty_service.extract_member_token("TU-LR1:abc")
    assert exc.value.code == "wrong_token_type"


def test_social_url_canonicalization():
    assert loyalty_service.canonicalize_social_url(
        "instagram", "https://www.instagram.com/p/abc/?utm_source=test#comments"
    ) == "https://instagram.com/p/abc"
    with pytest.raises(loyalty_service.LoyaltyError):
        loyalty_service.canonicalize_social_url("instagram", "http://instagram.com/p/abc")
    with pytest.raises(loyalty_service.LoyaltyError):
        loyalty_service.canonicalize_social_url("instagram", "https://example.com/post")


def test_social_submission_uses_bare_conflict_target_for_partial_index():
    source = inspect.getsource(loyalty_service.submit_social_post)
    assert "ON CONFLICT DO NOTHING" in source
    assert "ON CONFLICT (brand_id, canonical_url)" not in source


def _function_source(module) -> str:
    return "\n".join(
        inspect.getsource(obj)
        for _, obj in inspect.getmembers(module, inspect.isfunction)
        if obj.__module__ == module.__name__
    )


def test_award_uses_idempotent_insert_and_never_catches_unique_violation():
    source = inspect.getsource(loyalty_service.award_event)
    assert "ON CONFLICT (brand_id, account_id, reason, reference_id)" in source
    assert "RETURNING id" in source
    assert "UniqueViolationError" not in _function_source(loyalty_service)


def test_loyalty_service_does_not_touch_global_economy():
    source = _function_source(loyalty_service)
    assert "tellus_points_balances" not in source
    assert "tellus_points_ledger" not in source
    assert "tellus_reward_listings" not in source
    assert "tellus_redemptions" not in source


def test_award_balance_lock_precedes_cap_query():
    source = inspect.getsource(loyalty_service.award_event)
    assert source.index("FOR UPDATE") < source.index("earned_today")
