"""Huume's per-turn tier routing (routing.py) and its wiring into the agent
loop (agent.py: planner model/config on call 1, executor on calls 2..N).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_routing.py -q
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from google.genai import types

from app.matcha.services.huume import agent, routing
from app.matcha.services.huume.tools import TOOLS


class TestHasPendingConfirmable:
    def test_staged_action_is_pending(self):
        assert routing.has_pending_confirmable({"huume_action": {"status": "proposed"}}) is True

    def test_filed_action_is_not_pending(self):
        assert routing.has_pending_confirmable({"huume_action": {"status": "filed"}}) is False

    def test_no_action_no_plans_is_not_pending(self):
        assert routing.has_pending_confirmable({}) is False

    def test_active_plan_is_pending(self):
        for status in ("proposed", "approved", "executing"):
            assert routing.has_pending_confirmable({"huume_plans": {"offer-1": {"status": status}}}) is True

    def test_done_plan_is_not_pending(self):
        assert routing.has_pending_confirmable({"huume_plans": {"offer-1": {"status": "done"}}}) is False

    def test_malformed_state_never_raises(self):
        assert routing.has_pending_confirmable({"huume_action": "not-a-dict"}) is False
        assert routing.has_pending_confirmable({"huume_plans": "not-a-dict"}) is False
        assert routing.has_pending_confirmable({"huume_plans": {"x": "not-a-dict"}}) is False
        assert routing.has_pending_confirmable(None) is False  # type: ignore[arg-type]


class TestResolveTier:
    def test_confirm_shaped_with_pending_action_is_lite(self):
        state = {"huume_action": {"status": "proposed"}}
        assert routing.resolve_tier("yes, confirm", current_state=state) == "lite"
        assert routing.resolve_tier("approve it", current_state=state) == "lite"
        assert routing.resolve_tier("go ahead", current_state=state) == "lite"

    def test_confirm_shaped_without_pending_is_not_lite(self):
        assert routing.resolve_tier("yes", current_state={}) != "lite"

    def test_intent_hint_routes_deep(self):
        state = {}
        assert routing.resolve_tier("which incidents need disciplinary action?", current_state=state) == "deep"
        assert routing.resolve_tier("show me pending approvals", current_state=state) == "deep"

    def test_analytical_question_routes_deep(self):
        assert routing.resolve_tier("why does this keep happening?", current_state={}) == "deep"
        assert routing.resolve_tier("what should I do about this employee?", current_state={}) == "deep"

    def test_long_narrative_routes_deep(self):
        long_msg = "a" * 300
        assert routing.resolve_tier(long_msg, current_state={}) == "deep"

    def test_multi_newline_message_routes_deep(self):
        msg = "line one\nline two\nline three\nline four"
        assert routing.resolve_tier(msg, current_state={}) == "deep"

    def test_plain_short_ask_is_fallback(self):
        assert routing.resolve_tier("what's maria's start date?", current_state={}) == routing.FALLBACK_TIER

    def test_empty_or_none_message_is_fallback(self):
        assert routing.resolve_tier("", current_state={}) == routing.FALLBACK_TIER
        assert routing.resolve_tier(None, current_state={}) == routing.FALLBACK_TIER  # type: ignore[arg-type]

    def test_fallback_is_never_lite(self):
        # Merlin's own rule: unsure lands in the middle, never the cheap tier.
        assert routing.FALLBACK_TIER != "lite"

    def test_poisoned_current_state_falls_back_not_raises(self):
        assert routing.resolve_tier("yes", current_state="not-a-dict") == routing.FALLBACK_TIER  # type: ignore[arg-type]


class TestHintIndex:
    def test_every_discovery_tool_contributes_at_least_one_hint(self):
        discovery_names = {t.name for t in TOOLS if t.discovery}
        hinted_names = {name for _hint, name in routing.HINT_INDEX}
        assert discovery_names <= hinted_names

    def test_hints_are_lowercase(self):
        for hint, _name in routing.HINT_INDEX:
            assert hint == hint.lower()

    def test_build_hint_index_is_pure_and_matches_module_constant(self):
        assert routing.build_hint_index(TOOLS) == routing.HINT_INDEX


class TestThinkingConfig:
    def test_none_omits_config(self):
        assert routing.thinking_config(None) is None

    def test_none_level_sets_zero_budget(self):
        cfg = routing.thinking_config("none")
        assert isinstance(cfg, types.ThinkingConfig)
        assert cfg.thinking_budget == 0

    def test_high_sets_thinking_level(self):
        cfg = routing.thinking_config("high")
        assert cfg.thinking_level == "HIGH"

    def test_low_sets_thinking_level(self):
        cfg = routing.thinking_config("low")
        assert cfg.thinking_level == "LOW"


class TestTiersCatalog:
    def test_three_tiers_registered(self):
        assert set(routing.TIERS) == {"lite", "standard", "deep"}

    def test_lite_uses_zero_thinking_both_calls(self):
        tier = routing.TIERS["lite"]
        assert tier.planner_thinking == "none"
        assert tier.executor_thinking == "none"

    def test_standard_omits_thinking_config_both_calls(self):
        tier = routing.TIERS["standard"]
        assert tier.planner_thinking is None
        assert tier.executor_thinking is None

    def test_deep_thinks_hard_to_plan_low_to_execute(self):
        tier = routing.TIERS["deep"]
        assert tier.planner_thinking == "high"
        assert tier.executor_thinking == "low"


# ---- agent.py wiring: fake genai client records (model, config) per call ----


def _fake_call(name, args):
    return types.FunctionCall(name=name, args=args)


def _fake_part(function_call=None):
    return types.Part(function_call=function_call)


def _fake_response(parts=None, text=None):
    resp = MagicMock()
    resp.usage_metadata = None
    resp.text = text
    candidate = MagicMock()
    candidate.content = MagicMock()
    candidate.content.parts = parts or []
    resp.candidates = [candidate]
    return resp


class _NoopRateLimiter:
    async def check_limit(self, *a, **kw):
        return None

    async def record_call(self, *a, **kw):
        return None


@pytest.mark.asyncio
async def test_agent_loop_uses_planner_config_then_executor_config(monkeypatch):
    """Two model calls in one turn: call 1 (a tool call) must use the tier's
    planner model/thinking; call 2 (the tool-result follow-up, which ends the
    turn) must use the executor's."""
    recorded = []

    async def _generate(*, model, contents, config):
        recorded.append({"model": model, "thinking": config.thinking_config})
        if len(recorded) == 1:
            return _fake_response(parts=[_fake_part(_fake_call("check_offer_status", {"offer_id": "abc"}))])
        return _fake_response(parts=[], text="Done.")

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=_generate)
    monkeypatch.setattr(agent, "get_genai_client", lambda: client)
    monkeypatch.setattr(agent, "GeminiRateLimiter", _NoopRateLimiter)
    monkeypatch.setattr(
        agent.onboarding_skill, "check_offer_status", AsyncMock(return_value={"status": "ok", "offer_status": "pending"}),
    )

    frames = [
        f async for f in agent.run_huume_turn(
            thread_id=uuid4(), company_id=uuid4(), user_id=uuid4(), user_role="client",
            history=[{"role": "user", "content": "which incidents need disciplinary action?"}],
            current_state={}, company_name="Acme", features={"huume": True, "matcha_work": True},
            integrations={},
        )
    ]

    assert len(recorded) == 2
    assert recorded[0]["thinking"].thinking_level == "HIGH"   # deep tier, planner call
    assert recorded[1]["thinking"].thinking_level == "LOW"    # deep tier, executor call

    result_frame = next(f for f in frames if f["type"] == "huume_result")
    assert result_frame["data"]["token_usage"]["tier"] == "deep"


@pytest.mark.asyncio
async def test_agent_loop_standard_tier_omits_thinking_config(monkeypatch):
    async def _generate(*, model, contents, config):
        return _fake_response(parts=[], text="Sure, here you go.")

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=_generate)
    monkeypatch.setattr(agent, "get_genai_client", lambda: client)
    monkeypatch.setattr(agent, "GeminiRateLimiter", _NoopRateLimiter)

    frames = [
        f async for f in agent.run_huume_turn(
            thread_id=uuid4(), company_id=uuid4(), user_id=uuid4(), user_role="client",
            history=[{"role": "user", "content": "what's maria's start date?"}],
            current_state={}, company_name="Acme", features={"huume": True, "matcha_work": True},
            integrations={},
        )
    ]

    result_frame = next(f for f in frames if f["type"] == "huume_result")
    assert result_frame["data"]["token_usage"]["tier"] == "standard"


@pytest.mark.asyncio
async def test_agent_loop_confirm_turn_is_lite_tier(monkeypatch):
    async def _generate(*, model, contents, config):
        return _fake_response(parts=[], text="Confirmed.")

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=_generate)
    monkeypatch.setattr(agent, "get_genai_client", lambda: client)
    monkeypatch.setattr(agent, "GeminiRateLimiter", _NoopRateLimiter)

    frames = [
        f async for f in agent.run_huume_turn(
            thread_id=uuid4(), company_id=uuid4(), user_id=uuid4(), user_role="client",
            history=[{"role": "user", "content": "yes, confirm"}],
            current_state={"huume_action": {"status": "proposed", "type": "send_offer", "offer_id": "x"}},
            company_name="Acme", features={"huume": True, "matcha_work": True}, integrations={},
        )
    ]

    result_frame = next(f for f in frames if f["type"] == "huume_result")
    assert result_frame["data"]["token_usage"]["tier"] == "lite"
