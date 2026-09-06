"""Huume's per-turn tier routing (routing.py) and its wiring into the agent
loop (agent.py: planner model/config on call 1, executor on calls 2..N).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_routing.py -q
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from google.genai import types

from app.matcha.services.huume import agent, routing
from app.matcha.services.huume.prompt import build_discovery_block, build_system_prompt
from app.matcha.services.huume.tools import TOOLS


class TestLastUserText:
    """`agent._last_user_text` — feeds `routing.resolve_tier`. Matches
    `role == "user"` explicitly, not `role != "assistant"`, so a future
    non-user/non-assistant role (a genuine system notice) can't silently
    start driving tier selection."""

    def test_picks_the_last_user_message(self):
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
        assert agent._last_user_text(history) == "second"

    def test_trailing_assistant_message_is_skipped(self):
        history = [
            {"role": "user", "content": "which incidents need discipline?"},
            {"role": "assistant", "content": "Here's what I found."},
        ]
        assert agent._last_user_text(history) == "which incidents need discipline?"

    def test_non_user_non_assistant_role_is_not_picked_up(self):
        history = [
            {"role": "user", "content": "real question"},
            {"role": "system", "content": "Offer accepted by candidate."},
        ]
        assert agent._last_user_text(history) == "real question"

    def test_empty_history_is_empty_string(self):
        assert agent._last_user_text([]) == ""
        assert agent._last_user_text(None) == ""


class TestHasPendingConfirmable:
    def test_staged_action_is_pending(self):
        assert routing.has_pending_confirmable({"huume_action": {"status": "proposed"}}) is True

    def test_filed_action_is_not_pending(self):
        assert routing.has_pending_confirmable({"huume_action": {"status": "filed"}}) is False

    def test_no_action_no_plans_is_not_pending(self):
        assert routing.has_pending_confirmable({}) is False

    def test_proposed_plan_is_pending(self):
        assert routing.has_pending_confirmable({"huume_plans": {"offer-1": {"status": "proposed"}}}) is True

    def test_approved_or_executing_plan_is_not_pending(self):
        # Narrower than actions._ACTIVE_PLAN_STATUSES on purpose: an approved
        # or still-executing plan already got its "yes" (or is stuck mid-run,
        # which merge_executed_steps deliberately allows to persist) — it is
        # not waiting on the admin to confirm anything, so a later bare "ok"
        # in the thread must not keep routing to the thinking-off lite tier.
        for status in ("approved", "executing"):
            assert routing.has_pending_confirmable({"huume_plans": {"offer-1": {"status": status}}}) is False

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

    def test_confirm_prefix_on_a_real_question_routes_deep_not_lite(self):
        # _CONFIRM_RE is a PREFIX match ("^(yes|ok(ay)?|...)\b") with only an
        # 8-word cap — a discovery/analytical question that happens to open
        # with a confirm word must still win on its content, even with a
        # plan staged (the exact shape that used to slip through to lite).
        state = {"huume_action": {"status": "proposed"}}
        assert routing.resolve_tier("ok which incidents need disciplinary action?", current_state=state) == "deep"
        assert routing.resolve_tier("yeah what should we do about the ER case", current_state=state) == "deep"

    def test_approved_plan_no_longer_makes_a_bare_confirm_lite(self):
        # Companion to has_pending_confirmable's own test: an approved plan
        # already got its yes, so a later bare "ok" is just an ordinary
        # short message, not a confirm turn.
        state = {"huume_plans": {"offer-1": {"status": "approved"}}}
        assert routing.resolve_tier("ok", current_state=state) != "lite"

    def test_intent_hint_routes_deep(self):
        state = {}
        assert routing.resolve_tier("which incidents need disciplinary action?", current_state=state) == "deep"
        assert routing.resolve_tier("show me pending approvals", current_state=state) == "deep"

    def test_assign_shift_intent_hint_routes_deep(self):
        # "Assign Elena to one of them" previously fell to `standard` (no
        # matching intent_hint), understating what the message needed. The
        # hint is deliberately multi-word ("assign a shift"/"put someone
        # on") — a bare "assign" would also substring-match training/PTO
        # assignment asks that have nothing to do with scheduling, see
        # test_training_assignment_phrasing_does_not_hit_schedule_hints.
        assert routing.resolve_tier("can you put someone on the closer shift", current_state={}) == "deep"
        assert routing.resolve_tier("please assign a shift to Elena", current_state={}) == "deep"

    def test_training_assignment_phrasing_does_not_hit_schedule_hints(self):
        # A bare "assign" intent hint used to substring-match this and
        # route it at propose_schedule_change instead of assign_training.
        from app.matcha.services.huume.tools import TOOLS_BY_NAME
        msg = "assign the food-safety training to Maria"
        schedule_hints = TOOLS_BY_NAME["propose_schedule_change"].intent_hints
        assert not any(hint in msg.lower() for hint in schedule_hints)

    def test_send_offer_by_name_hint_routes_deep(self):
        assert routing.resolve_tier("can you send the offer letter to maria please", current_state={}) == "deep"

    def test_list_assets_hint_routes_deep(self):
        assert routing.resolve_tier("what have we made in this thread so far", current_state={}) == "deep"

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


class TestDiscoveryBlock:
    def test_every_discovery_tool_named_in_block(self):
        block = build_discovery_block(TOOLS)
        for t in TOOLS:
            if t.discovery:
                assert t.name in block

    def test_no_discovery_tools_returns_empty(self):
        assert build_discovery_block([]) == ""

    def test_block_is_present_in_full_system_prompt(self):
        prompt = build_system_prompt(company_name="Acme", today="2026-07-29")
        assert "## Broad questions" in prompt
        assert "find_discipline_candidates" in prompt


class TestTiersCatalog:
    def test_three_tiers_registered(self):
        assert set(routing.TIERS) == {"lite", "standard", "deep"}

    def test_lite_uses_luna_for_both_calls(self):
        tier = routing.TIERS["lite"]
        assert tier.planner_model == routing.LUNA
        assert tier.executor_model == routing.LUNA

    def test_standard_and_deep_also_use_luna(self):
        assert routing.TIERS["standard"].planner_model == routing.LUNA
        assert routing.TIERS["standard"].executor_model == routing.LUNA
        assert routing.TIERS["deep"].planner_model == routing.LUNA
        assert routing.TIERS["deep"].executor_model == routing.LUNA

# ---- agent.py wiring: fake Luna adapter records (model, config) per call ----


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
    """Planner and tool-result calls both remain pinned to Luna."""
    recorded = []

    async def _generate(*, model, contents, config, **_request_options):
        recorded.append({"model": model, "thinking": config.thinking_config})
        if len(recorded) == 1:
            return _fake_response(parts=[_fake_part(_fake_call("check_offer_status", {"offer_id": "abc"}))])
        return _fake_response(parts=[], text="Done.")

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=_generate)
    monkeypatch.setattr(agent, "get_luna_client", lambda: client)
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
    assert recorded == [
        {"model": routing.LUNA, "thinking": None},
        {"model": routing.LUNA, "thinking": None},
    ]

    result_frame = next(f for f in frames if f["type"] == "huume_result")
    assert result_frame["data"]["token_usage"]["tier"] == "deep"


@pytest.mark.asyncio
async def test_agent_loop_standard_tier_omits_thinking_config(monkeypatch):
    async def _generate(*, model, contents, config, **_request_options):
        return _fake_response(parts=[], text="Sure, here you go.")

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=_generate)
    monkeypatch.setattr(agent, "get_luna_client", lambda: client)
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
    recorded = []

    async def _generate(*, model, contents, config, **_request_options):
        recorded.append(model)
        return _fake_response(parts=[], text="Confirmed.")

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=_generate)
    monkeypatch.setattr(agent, "get_luna_client", lambda: client)
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
    assert recorded == [routing.LUNA]
