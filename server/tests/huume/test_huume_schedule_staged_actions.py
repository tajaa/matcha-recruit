"""Regression tests for a real, always-reproducing crash found 2026-08-26 by
manually stress-testing the schedule assistant: `propose_assignment_note`,
`propose_meal_break_waiver`, and `propose_eligibility_case_decision` all threw
`UnboundLocalError: cannot access local variable 'get_connection'`.

Root cause: `agent.py`'s unrelated `draft_disciplinary_action` branch has a
local `from app.database import get_connection` — one local import ANYWHERE
in `call_tool`'s body makes Python treat the name as local to the WHOLE
function, so the three branches below (which reference the bare name without
importing it themselves) blow up before that unrelated branch ever runs.
Fixed by giving each of the three its own local import, same as the existing
`_get_connection` alias a few branches down already did correctly.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from google.genai import types

from app.matcha.services.huume import agent, schedule_skill
from app.matcha.services.scheduling import week_builder
from app.matcha.services.huume.scope import (
    HuumeSurfaceContext,
    SCHEDULE_LOOKUP_TOPICS,
    SCHEDULE_TOOLS,
)


def _schedule_surface_context() -> HuumeSurfaceContext:
    return HuumeSurfaceContext(
        surface="schedule_assistant",
        location_id=uuid4(),
        week_start=date(2026, 8, 23),
        week_end=date(2026, 8, 29),
        allowed_tools=SCHEDULE_TOOLS,
        allowed_lookup_topics=SCHEDULE_LOOKUP_TOPICS,
    )


class _NoopRateLimiter:
    async def check_limit(self, *args, **kwargs):
        return None

    async def record_call(self, *args, **kwargs):
        return None


def _fake_call(name: str, args: dict) -> types.FunctionCall:
    return types.FunctionCall(name=name, args=args)


def _fake_response(*, calls=None, text=None):
    response = MagicMock()
    response.usage_metadata = SimpleNamespace(
        prompt_token_count=0, candidates_token_count=0, total_token_count=0,
        thoughts_token_count=0, cached_content_token_count=0,
    )
    response.text = text
    candidate = MagicMock()
    candidate.content = MagicMock()
    candidate.content.parts = [types.Part(function_call=call) for call in (calls or [])]
    response.candidates = [candidate]
    return response


def _connection_context(monkeypatch, *, fetchval=None, fetchrow=None):
    connection = MagicMock()
    connection.fetchval = AsyncMock(return_value=fetchval)
    connection.fetchrow = AsyncMock(return_value=fetchrow)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=connection)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=context))
    return connection


async def _run_turn(monkeypatch, responses, *, fetchval=None, fetchrow=None):
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=responses)
    monkeypatch.setattr(agent, "get_luna_client", lambda: client)
    monkeypatch.setattr(agent, "GeminiRateLimiter", _NoopRateLimiter)
    _connection_context(monkeypatch, fetchval=fetchval, fetchrow=fetchrow)

    frames = [
        frame async for frame in agent.run_huume_turn(
            thread_id=uuid4(), company_id=uuid4(), user_id=uuid4(), user_role="client",
            history=[{"role": "user", "content": "stage something"}],
            company_name="Acme", current_state={}, features={
                "huume": True, "matcha_work": True, "employee_schedule": True,
            }, integrations={}, surface_context=_schedule_surface_context(),
        )
    ]
    return frames


def _result(frames):
    return next(frame["data"] for frame in frames if frame["type"] == "huume_result")


def _step_statuses(result):
    return [(step["tool"], step["status"]) for step in result["steps"]]


@pytest.mark.asyncio
async def test_propose_meal_break_waiver_does_not_crash(monkeypatch):
    call = _fake_call("propose_meal_break_waiver", {
        "employee_id": str(uuid4()), "on_file": True, "effective_from": "2026-08-26",
    })
    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="Staged.")],
        fetchval=True,  # employee_exists
    )
    result = _result(frames)
    assert ("propose_meal_break_waiver", "error") not in _step_statuses(result)
    assert result["state_updates"].get("huume_action", {}).get("type") == "meal_break_waiver"


@pytest.mark.asyncio
async def test_propose_assignment_note_does_not_crash(monkeypatch):
    call = _fake_call("propose_assignment_note", {
        "shift_id": str(uuid4()), "employee_id": str(uuid4()), "note": "Review POS training.",
    })
    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="Staged.")],
        fetchval=True,  # assignment_exists
    )
    result = _result(frames)
    assert ("propose_assignment_note", "error") not in _step_statuses(result)
    assert result["state_updates"].get("huume_action", {}).get("type") == "schedule_note"


@pytest.mark.asyncio
async def test_propose_eligibility_case_decision_does_not_crash(monkeypatch):
    case_id = uuid4()
    call = _fake_call("propose_eligibility_case_decision", {
        "case_id": str(case_id), "decision": "keep", "acknowledgement_confirmed": True,
        "acknowledgement_note": "Manager reviewed and accepts the risk in writing.",
    })
    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="Staged.")],
        fetchrow={
            "id": case_id, "employee_id": uuid4(), "requirement_type": "credential",
            "status": "open", "expires_at": None, "legal_basis": "state licensing law",
        },
    )
    result = _result(frames)
    assert ("propose_eligibility_case_decision", "error") not in _step_statuses(result)
    assert result["state_updates"].get("huume_action", {}).get("type") == "eligibility_case_decision"


@pytest.mark.asyncio
async def test_first_staged_action_owns_slot_and_later_action_types_are_deferred(monkeypatch):
    """The full-scheduler repro requested a shift assignment, an assignment
    note, and a meal-break waiver in one message. All three tools used to
    return `status=staged` while overwriting the same state slot, so only the
    waiver survived. Keep the schedule proposal and tell the model exactly
    which later writes were not staged."""
    monkeypatch.setattr(schedule_skill, "propose", AsyncMock(return_value={
        "status": "ready", "proposal_id": str(uuid4()),
        "pill_text": "Assign Bea to Thursday closer.", "operation_count": 1,
    }))
    calls = [
        _fake_call("propose_schedule_change", {
            "kind": "assign", "to_employee_name": "Bea Haddad",
            "target_date": "2026-08-27", "target_time_hint": "17:00",
            "target_staffing_hint": "unstaffed",
        }),
        _fake_call("propose_assignment_note", {
            "shift_id": str(uuid4()), "employee_id": str(uuid4()),
            "note": "Review the new POS training before your shift.",
        }),
        _fake_call("propose_meal_break_waiver", {
            "employee_id": str(uuid4()), "on_file": True,
            "effective_from": "2026-08-26",
        }),
    ]

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=calls), _fake_response(text="The schedule change is staged; the note and waiver are deferred.")],
    )
    result = _result(frames)

    assert result["state_updates"]["huume_action"]["type"] == "schedule_change"
    assert _step_statuses(result) == [
        ("propose_schedule_change", "ok"),
        ("propose_assignment_note", "skipped"),
        ("propose_meal_break_waiver", "skipped"),
    ]
    deferred = [step["detail"] for step in result["steps"] if step["status"] == "skipped"]
    assert any("did not stage the assignment note" in detail for detail in deferred)
    assert any("did not stage the meal-break waiver" in detail for detail in deferred)


@pytest.mark.asyncio
async def test_build_week_schedule_stages_scoped_preview(monkeypatch):
    run_id = uuid4()
    monkeypatch.setattr(week_builder, "propose_week_draft", AsyncMock(return_value={
        "status": "ready",
        "generation_run_id": str(run_id),
        "source_mode": "existing",
        "summary": "Built 2 of 2 positions.",
        "metrics": {"shift_count": 1, "required_positions": 2, "filled_positions": 2, "open_positions": 0},
        "unfilled": [],
        "schedule_preview": [{
            "shift_key": "shift-1", "starts_at": "2026-08-24T09:00:00+00:00",
            "ends_at": "2026-08-24T17:00:00+00:00", "role": "Floor",
            "required_staff": 2, "assignment_names": ["Amy", "Ben"],
        }],
        "preview_truncated": False,
    }))
    call = _fake_call("build_week_schedule", {"source_mode": "auto"})

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="The generated week is ready for approval.")],
    )
    result = _result(frames)
    action = result["state_updates"]["huume_action"]

    assert action["type"] == "schedule_week_draft"
    assert action["generation_run_id"] == str(run_id)
    assert action["location_id"]
    assert action["week_start"] == "2026-08-23"
    assert action["schedule_preview"][0]["assignment_names"] == ["Amy", "Ben"]
    assert ("build_week_schedule", "ok") in _step_statuses(result)
