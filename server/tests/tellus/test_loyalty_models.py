"""Pure validation tests for the brand loyalty configuration contract."""
import pytest

from app.tellus.models.loyalty import (
    LoyaltyProgramPut,
    LoyaltyPurchaseIn,
    LoyaltyVisitIn,
)


def rule(event_key: str, *, active: bool = True) -> dict:
    if event_key == "purchase":
        return {
            "event_key": event_key,
            "award_type": "per_dollar",
            "points_per_dollar": 1,
            "min_purchase_cents": 100,
            "max_points_per_event": 1000,
            "is_active": active,
        }
    return {
        "event_key": event_key,
        "award_type": "fixed",
        "fixed_points": 10,
        "is_active": active,
    }


def program(**overrides):
    data = {
        "name": "Rewards",
        "point_singular": "point",
        "point_plural": "points",
        "status": "draft",
        "counter_mode": "purchase",
        "rules": [rule(key, active=key != "visit") for key in (
            "visit", "purchase", "review", "board_reply", "follow", "social_post"
        )],
        "tiers": [
            {"tier_key": "bronze", "threshold_points": 0},
            {"tier_key": "silver", "threshold_points": 500},
            {"tier_key": "gold", "threshold_points": 1500},
        ],
    }
    data.update(overrides)
    return data


def test_valid_program_config():
    value = LoyaltyProgramPut(**program())
    assert value.counter_mode == "purchase"


def test_program_requires_all_event_keys():
    data = program(rules=[rule("visit")])
    with pytest.raises(ValueError):
        LoyaltyProgramPut(**data)


def test_program_rejects_duplicate_event_key():
    rules = [rule(key) for key in ("visit", "purchase", "review", "board_reply", "follow", "social_post")]
    rules[-1]["event_key"] = "visit"
    with pytest.raises(ValueError, match="exactly one rule"):
        LoyaltyProgramPut(**program(rules=rules))


def test_bronze_threshold_must_be_zero():
    tiers = program()["tiers"]
    tiers[0]["threshold_points"] = 1
    with pytest.raises(ValueError, match="Bronze"):
        LoyaltyProgramPut(**program(tiers=tiers))


def test_silver_must_be_below_gold():
    tiers = program()["tiers"]
    tiers[1]["threshold_points"] = 1500
    with pytest.raises(ValueError, match="ordered"):
        LoyaltyProgramPut(**program(tiers=tiers))


def test_purchase_rule_requires_per_dollar():
    rules = program()["rules"]
    rules[1] = rule("purchase")
    rules[1]["award_type"] = "fixed"
    with pytest.raises(ValueError, match="per dollar"):
        LoyaltyProgramPut(**program(rules=rules))


def test_non_purchase_rule_rejects_per_dollar():
    rules = program()["rules"]
    rules[0] = rule("visit")
    rules[0]["award_type"] = "per_dollar"
    with pytest.raises(ValueError, match="fixed"):
        LoyaltyProgramPut(**program(rules=rules))


def test_visit_mode_requires_active_visit_rule():
    rules = program()["rules"]
    rules[0]["is_active"] = False
    with pytest.raises(ValueError, match="counter"):
        LoyaltyProgramPut(**program(counter_mode="visit", rules=rules))


def test_visit_body_forbids_amount():
    with pytest.raises(ValueError):
        LoyaltyVisitIn(member_token="abc", amount_cents=100)


def test_purchase_body_forbids_unknown_fields():
    with pytest.raises(ValueError):
        LoyaltyPurchaseIn(member_token="abc", amount_cents=100, currency="USD")


def test_purchase_amount_bounds():
    with pytest.raises(ValueError):
        LoyaltyPurchaseIn(member_token="abc", amount_cents=0)
    with pytest.raises(ValueError):
        LoyaltyPurchaseIn(member_token="abc", amount_cents=1_000_001)
