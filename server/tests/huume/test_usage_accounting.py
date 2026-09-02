"""Huume spend-accounting tests (no DB/network).

    cd server && ./venv/bin/python -m pytest tests/huume/test_usage_accounting.py -q

Covers: _accumulate_usage folding all five usage counters, Luna's internal
usage-event pricing, Responses token semantics, and the huume feature-label
constants the admin page's HUUME_FEATURE_PREFIX filter depends on.
"""
import inspect
from decimal import Decimal
from types import SimpleNamespace

from app.matcha.services.billing.model_pricing import (
    DEFAULT_PRICING, MODEL_PRICING, calculate_call_cost,
)
from app.matcha.services.huume.agent import _MODEL, _accumulate_usage
from app.matcha.services.huume.routing import LUNA


class TestAccumulateUsage:
    def test_folds_all_five_counters(self):
        total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                 "thinking_tokens": 0, "cached_tokens": 0}
        _accumulate_usage(total, SimpleNamespace(
            prompt_token_count=100, candidates_token_count=20,
            total_token_count=150, thoughts_token_count=30, cached_content_token_count=40))
        _accumulate_usage(total, SimpleNamespace(
            prompt_token_count=1, candidates_token_count=2,
            total_token_count=6, thoughts_token_count=3, cached_content_token_count=4))
        assert total == {"prompt_tokens": 101, "completion_tokens": 22,
                         "total_tokens": 156, "thinking_tokens": 33, "cached_tokens": 44}

    def test_missing_and_none_attrs_count_zero(self):
        total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                 "thinking_tokens": 0, "cached_tokens": 0}
        _accumulate_usage(total, SimpleNamespace())                       # attrs absent
        _accumulate_usage(total, SimpleNamespace(prompt_token_count=None,
                                                 thoughts_token_count=None))
        assert all(v == 0 for v in total.values())


class TestHuumeModelPricing:
    def test_huume_model_is_priced_not_default(self):
        # The loop's model must never fall back to DEFAULT_PRICING again.
        assert _MODEL in MODEL_PRICING
        assert MODEL_PRICING[_MODEL] != DEFAULT_PRICING

    def test_admin_ledger_prices_openai_cost(self):
        # Per-feature admin rows use exact provider tokens with Luna's
        # published rates; the organization Costs API remains invoice-level.
        from app.core.services.ai_usage import PRICING
        assert PRICING[("openai", LUNA)] == (0.20, 1.20)

    def test_million_token_cost(self):
        cost = calculate_call_cost(LUNA, 1_000_000, 1_000_000)
        assert cost == Decimal("1.400000")   # 0.20 in + 1.20 out

    def test_cached_input_uses_cached_rate(self):
        cost = calculate_call_cost(LUNA, 1_000_000, 0, cached_tokens=1_000_000)
        assert cost == Decimal("0.020000")


class TestThinkingBilling:
    def test_responses_reasoning_is_already_in_output_tokens(self):
        with_thinking = calculate_call_cost(LUNA, 0, 100, thinking_tokens=100)
        as_output = calculate_call_cost(LUNA, 0, 100)
        assert with_thinking == as_output

    def test_omitted_and_none_are_identical(self):
        assert calculate_call_cost(LUNA, 500, 500) == \
               calculate_call_cost(LUNA, 500, 500, thinking_tokens=None)


class TestFeatureLabels:
    def test_pilot_skills_carry_huume_labels(self):
        # The admin page filters by_feature on 'matcha.huume.' — a renamed or
        # dropped feature_scope label silently vanishes from the Huume block.
        from app.matcha.services.huume import handbook_skill, legal_skill
        assert 'feature_scope("matcha.huume.legal_pilot")' in inspect.getsource(legal_skill)
        assert 'feature_scope("matcha.huume.handbook_pilot")' in inspect.getsource(handbook_skill)

    def test_loop_label_shares_the_prefix(self):
        from app.matcha.services.huume import agent
        assert 'feature_scope("matcha.huume.loop")' in inspect.getsource(agent)
