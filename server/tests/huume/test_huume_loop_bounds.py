"""Regression tests for Huume's bounded schedule loop.

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_loop_bounds.py -q

These tests stub Gemini and the schedule resolver. No database or external
Gemini call is made; the only connection context is the stage-turn seam in
agent.py, which is replaced with an inert async context manager.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from google.genai import types

from app.matcha.services.huume import agent, schedule_skill


class _NoopRateLimiter:
    async def check_limit(self, *args, **kwargs):
        return None

    async def record_call(self, *args, **kwargs):
        return None


def _fake_call(name: str, args: dict) -> types.FunctionCall:
    return types.FunctionCall(name=name, args=args)


def _fake_response(*, calls=None, text=None, prompt_tokens=0):
    response = MagicMock()
    response.usage_metadata = SimpleNamespace(
        prompt_token_count=prompt_tokens,
        candidates_token_count=0,
        total_token_count=prompt_tokens,
        thoughts_token_count=0,
        cached_content_token_count=0,
    )
    response.text = text
    candidate = MagicMock()
    candidate.content = MagicMock()
    candidate.content.parts = [types.Part(function_call=call) for call in (calls or [])]
    response.candidates = [candidate]
    return response


def _connection_context(monkeypatch):
    connection = MagicMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=connection)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=context))


async def _run_turn(
    monkeypatch,
    responses,
    *,
    schedule_result=None,
    schedule_execute_result=None,
    current_state=None,
    history_text="assign Elena",
):
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=responses)
    monkeypatch.setattr(agent, "get_genai_client", lambda: client)
    monkeypatch.setattr(agent, "GeminiRateLimiter", _NoopRateLimiter)
    _connection_context(monkeypatch)
    if schedule_result is not None:
        monkeypatch.setattr(schedule_skill, "propose", AsyncMock(return_value=schedule_result))
    if schedule_execute_result is not None:
        monkeypatch.setattr(schedule_skill, "execute", AsyncMock(return_value=schedule_execute_result))

    frames = [
        frame async for frame in agent.run_huume_turn(
            thread_id=uuid4(), company_id=uuid4(), user_id=uuid4(), user_role="client",
            history=[{"role": "user", "content": history_text}],
            company_name="Acme", current_state=current_state or {}, features={
                "huume": True, "matcha_work": True, "employee_schedule": True,
            }, integrations={},
        )
    ]
    return frames, client


def _result(frames):
    return next(frame["data"] for frame in frames if frame["type"] == "huume_result")


@pytest.mark.asyncio
async def test_schedule_clarification_stops_before_followup_model_call(monkeypatch):
    schedule_result = {
        "status": "clarify",
        "message": "Which shift did you mean?\nReply with the shift time.",
    }
    responses = [
        _fake_response(calls=[_fake_call(
            "propose_schedule_change",
            {"kind": "assign", "target_date": "2026-08-07", "to_employee_name": "Elena"},
        )]),
        RuntimeError("a terminal clarification must not call Gemini again"),
    ]

    frames, client = await _run_turn(monkeypatch, responses, schedule_result=schedule_result)
    result = _result(frames)

    assert client.aio.models.generate_content.await_count == 1
    assert result["message"] == schedule_result["message"]
    assert result["model_calls"] == 1
    assert result["token_usage"]["stop_reason"] == "schedule_clarification"
    assert result["token_usage"]["tool_rejections"] == 1


@pytest.mark.asyncio
async def test_duplicate_schedule_call_in_same_batch_is_blocked(monkeypatch):
    schedule_result = {
        "status": "ready", "proposal_id": "proposal-1", "pill_text": "Schedule pill",
    }
    call = _fake_call(
        "propose_schedule_change",
        {"kind": "assign", "target_date": "2026-08-07", "to_employee_name": "Elena"},
    )
    frames, client = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call, call])],
        schedule_result=schedule_result,
    )
    result = _result(frames)

    assert client.aio.models.generate_content.await_count == 1
    assert schedule_skill.propose.await_count == 1
    assert result["token_usage"]["duplicate_tool_calls_blocked"] == 1
    assert result["token_usage"]["stop_reason"] == "schedule_duplicate_blocked"
    assert any(
        step["status"] == "rejected" and step["label"] == "Schedule change retry blocked"
        for step in result["steps"]
    )


@pytest.mark.asyncio
async def test_changed_schedule_retry_hits_per_turn_schedule_cap(monkeypatch):
    schedule_result = {
        "status": "ready", "proposal_id": "proposal-1", "pill_text": "Schedule pill",
    }
    calls = [
        _fake_call(
            "propose_schedule_change",
            {"kind": "assign", "target_date": "2026-08-07", "target_time_hint": "8am", "to_employee_name": "Elena"},
        ),
        _fake_call(
            "propose_schedule_change",
            {"kind": "assign", "target_date": "2026-08-07", "target_time_hint": "12:30pm", "to_employee_name": "Elena"},
        ),
    ]
    frames, _client = await _run_turn(monkeypatch, [_fake_response(calls=calls)], schedule_result=schedule_result)
    result = _result(frames)

    assert schedule_skill.propose.await_count == 1
    assert result["token_usage"]["schedule_proposal_attempts"] == 1
    assert result["token_usage"]["tool_retry_limit_blocks"] == 1
    assert result["token_usage"]["stop_reason"] == "schedule_retry_limit"


@pytest.mark.asyncio
async def test_matching_confirm_call_is_not_blocked_by_schedule_cap(monkeypatch):
    confirm_id = "cc33dd44"
    responses = [_fake_response(calls=[_fake_call(
        "propose_schedule_change", {"kind": "assign", "confirm_id": confirm_id},
    )])]
    frames, _client = await _run_turn(
        monkeypatch,
        responses,
        current_state={
            "huume_action": {
                "type": "schedule_change", "status": "proposed",
                "confirm_id": confirm_id, "proposal_id": "proposal-1",
                "kind": "assign",
            },
        },
        schedule_execute_result={
            "status": "created", "message": "Schedule updated.",
            "record_id": "proposal-1", "bg_tasks": [],
        },
        history_text="yes, confirm the schedule change",
    )
    result = _result(frames)

    assert result["token_usage"]["schedule_proposal_attempts"] == 0
    assert result["token_usage"].get("stop_reason") is None
    assert result["steps"][-1]["status"] == "ok"


def test_tool_call_fingerprint_ignores_dictionary_order():
    first = agent._tool_call_fingerprint("propose_schedule_change", {"kind": "cancel", "target_date": "2026-08-07"})
    second = agent._tool_call_fingerprint("propose_schedule_change", {"target_date": "2026-08-07", "kind": "cancel"})
    assert first == second


def test_tool_call_fingerprint_changes_with_disambiguation_hint():
    first = agent._tool_call_fingerprint("propose_schedule_change", {"kind": "cancel", "target_time_hint": "8am"})
    second = agent._tool_call_fingerprint("propose_schedule_change", {"kind": "cancel", "target_time_hint": "12:30pm"})
    assert first != second


def test_turn_bound_reason_precedence():
    assert agent._turn_bound_reason(
        model_calls=agent._MAX_MODEL_CALLS,
        elapsed_seconds=agent._WALL_CLOCK_SECONDS,
        prompt_tokens=agent._MAX_TURN_PROMPT_TOKENS,
    ) == "model_call_limit"
    assert agent._turn_bound_reason(
        model_calls=0,
        elapsed_seconds=agent._WALL_CLOCK_SECONDS,
        prompt_tokens=agent._MAX_TURN_PROMPT_TOKENS,
    ) == "wall_clock_limit"
    assert agent._turn_bound_reason(
        model_calls=0,
        elapsed_seconds=0,
        prompt_tokens=agent._MAX_TURN_PROMPT_TOKENS,
    ) == "prompt_token_limit"
    assert agent._turn_bound_reason(model_calls=0, elapsed_seconds=0, prompt_tokens=0) is None


@pytest.mark.asyncio
async def test_prompt_token_limit_prevents_followup_model_call(monkeypatch):
    responses = [
        _fake_response(
            calls=[_fake_call("check_offer_status", {"offer_id": "offer-1"})],
            prompt_tokens=agent._MAX_TURN_PROMPT_TOKENS,
        ),
        RuntimeError("the prompt-token bound must prevent this call"),
    ]
    monkeypatch.setattr(
        agent.onboarding_skill,
        "check_offer_status",
        AsyncMock(return_value={"status": "ok", "offer_status": "pending"}),
    )

    frames, client = await _run_turn(
        monkeypatch, responses, history_text="what is the offer status?",
    )
    result = _result(frames)

    assert client.aio.models.generate_content.await_count == 1
    assert result["model_calls"] == 1
    assert result["token_usage"]["stop_reason"] == "prompt_token_limit"
    assert "AI budget" in result["message"]
