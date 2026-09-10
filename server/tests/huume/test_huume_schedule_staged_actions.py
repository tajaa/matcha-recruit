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

from app.matcha.services.huume import agent, schedule_profile_skill, schedule_skill
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
    def __init__(self, *args, **kwargs):
        pass

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


async def _run_turn(
    monkeypatch, responses, *, fetchval=None, fetchrow=None,
    current_state=None, user_text="stage something",
):
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=responses)
    monkeypatch.setattr(agent, "get_luna_client", lambda: client)
    monkeypatch.setattr(agent, "ApiRateLimiter", _NoopRateLimiter)
    _connection_context(monkeypatch, fetchval=fetchval, fetchrow=fetchrow)
    # The schedule prompt now embeds the location's saved profile; every test
    # here drives the tool loop, not that read.
    monkeypatch.setattr(
        schedule_profile_skill, "context_block", AsyncMock(return_value=""),
    )

    frames = [
        frame async for frame in agent.run_huume_turn(
            thread_id=uuid4(), company_id=uuid4(), user_id=uuid4(), user_role="client",
            history=[{"role": "user", "content": user_text}],
            company_name="Acme", current_state=current_state or {}, features={
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
        "review": {
            "proposal_id": str(run_id), "kind": "week_draft", "compliance_status": "advisory",
            "assignments": [{"shift_id": str(index), "verdict": "ok"} for index in range(25)],
            "rejected": [], "unfilled": [],
            "employees": [{"employee_id": "e1", "name": "Amy", "warnings": ["Spread the load."]}],
            "advisories": [{"message": str(index)} for index in range(25)],
            "findings": [{"detail": str(index)} for index in range(25)],
            "jurisdiction": {"state": "CA", "status": "curated", "message": "on file"},
        },
        "compliance_status": "advisory",
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
    assert action["review"]["assignment_count"] == 25
    assert action["review"]["advisory_count"] == 25
    assert action["review"]["employees"][0]["warnings"] == ["Spread the load."]
    assert not {"assignments", "unfilled", "advisories", "findings"} & action["review"].keys()
    assert ("build_week_schedule", "ok") in _step_statuses(result)


@pytest.mark.asyncio
async def test_save_location_profile_stages_resolved_setup(monkeypatch):
    """The staged dict carries what the SERVER resolved (job ids, materialized
    leader blocks), not the model's raw args — the confirm turn writes exactly
    what the manager was shown."""
    monkeypatch.setattr(schedule_profile_skill, "resolve_profile_args", AsyncMock(return_value={
        "status": "ok",
        "operating_hours": {"1": {"open": "08:00", "close": "17:00"}},
        "blocks": [{
            "name": "Opener", "role": "Barista", "job_id": str(uuid4()), "job_name": "Barista",
            "days_of_week": [1, 2, 3], "start_time": "08:00", "end_time": "16:00",
            "required_staff": 2, "break_minutes": 30,
        }],
        "leader_job_id": None, "leader_job_name": None, "notes": None, "template_name": None,
        "summary": "hours on 1 day, 1 shift block (2 positions/day-slot)",
    }))
    call = _fake_call("save_location_schedule_profile", {
        "operating_hours": {"1": {"open": "08:00", "close": "17:00"}},
        "blocks": [{
            "name": "Opener", "job_name": "Barista", "days_of_week": [1, 2, 3],
            "start_time": "08:00", "end_time": "16:00", "required_staff": 2,
        }],
    })

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="Staged the setup for your approval.")],
    )
    result = _result(frames)
    action = result["state_updates"]["huume_action"]

    assert action["type"] == "schedule_location_profile"
    assert action["status"] == "proposed"
    assert action["location_id"]
    assert len(action["confirm_id"]) == 8
    assert action["blocks"][0]["job_id"]
    assert ("save_location_schedule_profile", "ok") in _step_statuses(result)


@pytest.mark.asyncio
async def test_save_location_profile_clarify_offers_job_chips(monkeypatch):
    """An unresolvable job name becomes a tappable question, not a dead end."""
    monkeypatch.setattr(schedule_profile_skill, "resolve_profile_args", AsyncMock(return_value={
        "status": "clarify",
        "message": "There's no job named 'Barrista' at this location. Jobs here: Barista, Shift Lead.",
        "job_options": ["Barista", "Shift Lead"],
    }))
    call = _fake_call("save_location_schedule_profile", {
        "blocks": [{
            "name": "Opener", "job_name": "Barrista", "days_of_week": [1],
            "start_time": "08:00", "end_time": "16:00", "required_staff": 1,
        }],
    })

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="Which job did you mean?")],
    )
    result = _result(frames)

    assert "huume_action" not in result["state_updates"]
    choice = result["state_updates"]["huume_choice"]
    assert [option["label"] for option in choice["options"]] == ["Barista", "Shift Lead"]
    assert ("save_location_schedule_profile", "rejected") in _step_statuses(result)


@pytest.mark.asyncio
async def test_save_location_profile_confirm_requires_explicit_user_confirm(monkeypatch):
    """Echoing the confirm_id is not consent — the id is printed in the state
    block, so without this gate the model can approve its own proposal. A chip
    click sends an option label, never the word "confirm", so chips can't
    satisfy it either."""
    execute = AsyncMock(return_value={"status": "created", "record_id": str(uuid4())})
    monkeypatch.setattr(schedule_profile_skill, "execute", execute)
    staged = {
        "type": "schedule_location_profile", "status": "proposed", "confirm_id": "ab12cd34",
        "location_id": str(uuid4()), "operating_hours": {"1": {"open": "08:00", "close": "17:00"}},
        "blocks": [], "summary": "hours on 1 day",
    }
    call = _fake_call("save_location_schedule_profile", {"confirm_id": "ab12cd34"})

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="Still waiting on you.")],
        current_state={"huume_action": staged},
        user_text="also add a note about parking",
    )
    result = _result(frames)

    execute.assert_not_awaited()
    assert ("save_location_schedule_profile", "rejected") in _step_statuses(result)


@pytest.mark.asyncio
async def test_save_location_profile_executes_on_explicit_confirm(monkeypatch):
    execute = AsyncMock(return_value={"status": "created", "record_id": str(uuid4())})
    monkeypatch.setattr(schedule_profile_skill, "execute", execute)
    staged = {
        "type": "schedule_location_profile", "status": "proposed", "confirm_id": "ab12cd34",
        "location_id": str(uuid4()), "operating_hours": {"1": {"open": "08:00", "close": "17:00"}},
        "blocks": [], "summary": "hours on 1 day",
    }
    call = _fake_call("save_location_schedule_profile", {"confirm_id": "ab12cd34"})

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="Saved.")],
        current_state={"huume_action": staged},
        user_text="confirm",
    )
    result = _result(frames)

    execute.assert_awaited_once()
    assert result["state_updates"]["huume_action"]["status"] == "saved"


@pytest.mark.asyncio
async def test_duplicate_profile_confirm_blocked_within_one_turn(monkeypatch):
    """Parallel function calls can emit the same confirming call twice, and
    pre_turn_action is frozen for the whole turn — one confirm_id must execute
    at most once."""
    execute = AsyncMock(return_value={"status": "created", "record_id": str(uuid4())})
    monkeypatch.setattr(schedule_profile_skill, "execute", execute)
    staged = {
        "type": "schedule_location_profile", "status": "proposed", "confirm_id": "ab12cd34",
        "location_id": str(uuid4()), "operating_hours": {"1": {"open": "08:00", "close": "17:00"}},
        "blocks": [], "summary": "hours on 1 day",
    }
    calls = [
        _fake_call("save_location_schedule_profile", {"confirm_id": "ab12cd34"}),
        _fake_call("save_location_schedule_profile", {"confirm_id": "ab12cd34"}),
    ]

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=calls), _fake_response(text="Saved once.")],
        current_state={"huume_action": staged},
        user_text="confirm",
    )
    result = _result(frames)

    assert execute.await_count == 1
    assert ("save_location_schedule_profile", "rejected") in _step_statuses(result)


@pytest.mark.asyncio
async def test_finish_can_offer_tappable_options(monkeypatch):
    call = _fake_call("finish", {
        "message": "Which store are we scheduling?",
        "question": "Which store are we scheduling?",
        "options": ["Downtown", "Wilshire", "Downtown"],
    })
    frames = await _run_turn(monkeypatch, [_fake_response(calls=[call])])
    result = _result(frames)

    choice = result["state_updates"]["huume_choice"]
    # Deduped, and rendered as a single-select question.
    assert [option["label"] for option in choice["options"]] == ["Downtown", "Wilshire"]
    assert choice["kind"] == "single"


@pytest.mark.asyncio
async def test_stale_choice_is_cleared_when_the_turn_does_not_reissue_it(monkeypatch):
    """Chips answer one question. Left in place they invite the manager to tap
    an answer to something asked two turns ago."""
    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[_fake_call("finish", {"message": "Got it."})])],
        current_state={"huume_choice": {
            "question": "Which store?", "options": [{"label": "Downtown"}], "kind": "single",
        }},
    )
    result = _result(frames)
    assert result["state_updates"]["huume_choice"] is None


@pytest.mark.asyncio
async def test_no_choice_key_emitted_when_none_was_ever_set(monkeypatch):
    """An empty state_updates skips apply_update entirely; an unconditional
    clear would force a document version bump on every idle turn."""
    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[_fake_call("finish", {"message": "Got it."})])],
    )
    result = _result(frames)
    assert "huume_choice" not in result["state_updates"]


@pytest.mark.asyncio
async def test_profile_clarify_ends_the_turn_without_another_model_call(monkeypatch):
    """The clarify already names the location's real jobs, so a second model
    call can only re-ask what the manager can already read — the retry loop the
    August cost audit found. The deterministic message becomes the reply."""
    monkeypatch.setattr(schedule_profile_skill, "resolve_profile_args", AsyncMock(return_value={
        "status": "clarify",
        "message": "There's no job named 'Barrista' at this location. Jobs here: Barista, Shift Lead.",
        "job_options": ["Barista", "Shift Lead"],
    }))
    call = _fake_call("save_location_schedule_profile", {
        "blocks": [{
            "name": "Opener", "job_name": "Barrista", "days_of_week": [1],
            "start_time": "08:00", "end_time": "16:00", "required_staff": 1,
        }],
    })

    frames = await _run_turn(monkeypatch, [
        _fake_response(calls=[call]),
        AssertionError("the turn made a second model call after a schedule clarification"),
    ])
    result = _result(frames)

    assert result["message"] == (
        "There's no job named 'Barrista' at this location. Jobs here: Barista, Shift Lead."
    )
    assert result["token_usage"]["stop_reason"] == "schedule_clarification"
    assert result["model_calls"] == 1
    # The chips still ride along, so the manager can tap the answer.
    assert [option["label"] for option in result["state_updates"]["huume_choice"]["options"]] == [
        "Barista", "Shift Lead",
    ]


@pytest.mark.asyncio
async def test_week_template_clarify_ends_the_turn_too(monkeypatch):
    """Same rule for the builder's "which template?" — it lists the real saved
    templates, and re-asking costs a full model call per round."""
    monkeypatch.setattr(week_builder, "propose_week_draft", AsyncMock(return_value={
        "status": "clarify",
        "message": "Choose which week template to use.",
        "week_templates": [
            {"id": str(uuid4()), "name": "Downtown default week", "block_count": 4},
            {"id": str(uuid4()), "name": "Holiday week", "block_count": 3},
        ],
    }))

    frames = await _run_turn(monkeypatch, [
        _fake_response(calls=[_fake_call("build_week_schedule", {"source_mode": "auto"})]),
        AssertionError("the turn made a second model call after a schedule clarification"),
    ])
    result = _result(frames)

    assert result["message"] == "Choose which week template to use."
    assert result["token_usage"]["stop_reason"] == "schedule_clarification"
    assert [option["label"] for option in result["state_updates"]["huume_choice"]["options"]] == [
        "Downtown default week", "Holiday week",
    ]


@pytest.mark.asyncio
async def test_build_week_schedule_carries_findings_onto_the_staged_action(monkeypatch):
    """The card and the next turn's state block both read `findings` off the
    staged action; the tool response echoes them so the model can relay the
    gaps in the SAME turn it stages, instead of replying "week built"."""
    findings = [{
        "kind": "close_buffer_uncovered", "severity": "gap", "day": "2026-08-24",
        "window": {"start": "17:00", "end": "17:20"}, "minutes": 20,
        "detail": "Nobody is scheduled to close on Monday (17:00–17:20).",
    }]
    monkeypatch.setattr(week_builder, "propose_week_draft", AsyncMock(return_value={
        "status": "ready",
        "generation_run_id": str(uuid4()),
        "source_mode": "existing",
        "summary": "Built 2 of 2 positions. 1 coverage/break gap(s) need your review.",
        "metrics": {
            "shift_count": 1, "required_positions": 2, "filled_positions": 2,
            "open_positions": 0, "gap_count": 1, "operating_hours_known": True,
            "finding_counts": {"close_buffer_uncovered": 1},
        },
        "unfilled": [],
        "findings": findings,
        "schedule_preview": [],
        "preview_truncated": False,
    }))
    call = _fake_call("build_week_schedule", {"source_mode": "auto"})

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="Staged, with one gap at close.")],
    )
    result = _result(frames)
    action = result["state_updates"]["huume_action"]

    assert action["findings"] == findings
    assert action["metrics"]["gap_count"] == 1
    # Staged, not applied: a reported gap does not change the confirm contract.
    assert action["status"] == "proposed"


@pytest.mark.asyncio
async def test_save_location_profile_stages_the_leader_answer(monkeypatch):
    """`leader_required=False` is the answer that completes the setup. It is in
    the spec's `fields` whitelist, so it survives onto the staged dict — a
    field missing there is silently dropped and the confirm turn writes a
    profile the manager never saw."""
    monkeypatch.setattr(schedule_profile_skill, "resolve_profile_args", AsyncMock(return_value={
        "status": "ok",
        "operating_hours": {}, "blocks": [],
        "leader_job_id": None, "leader_job_name": None, "leader_required": False,
        "notes": None, "template_name": None,
        "summary": "no lead required on every shift",
    }))
    call = _fake_call("save_location_schedule_profile", {"leader_required": False})

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[call]), _fake_response(text="Staged that for your approval.")],
    )
    action = _result(frames)["state_updates"]["huume_action"]

    assert action["leader_required"] is False


def test_leader_required_is_in_the_staged_fields_whitelist():
    assert "leader_required" in agent._HR_OPS_TOOL_SPECS[
        "save_location_schedule_profile"
    ]["fields"]


@pytest.mark.asyncio
async def test_week_rules_refusal_ends_the_turn_and_offers_leader_chips(monkeypatch):
    """The builder refuses until the location's setup is saved. The refusal is
    terminal (no second model call) and, when the leader question is the only
    gap, it comes with the two answers as chips."""
    monkeypatch.setattr(week_builder, "propose_week_draft", AsyncMock(return_value={
        "status": "clarify",
        "message": (
            "I can't build this week yet — Downtown has no answer yet on whether a "
            "shift lead has to be on every shift."
        ),
        "setup_missing": ["leader_rule"],
    }))

    frames = await _run_turn(monkeypatch, [
        _fake_response(calls=[_fake_call("build_week_schedule", {"source_mode": "auto"})]),
        AssertionError("the turn made a second model call after a schedule clarification"),
    ])
    result = _result(frames)

    assert result["message"].startswith("I can't build this week yet")
    assert result["token_usage"]["stop_reason"] == "schedule_clarification"
    assert [o["label"] for o in result["state_updates"]["huume_choice"]["options"]] == ["Yes", "No"]
    assert "huume_action" not in result["state_updates"]


@pytest.mark.asyncio
async def test_a_multi_answer_setup_refusal_mints_no_chips(monkeypatch):
    """Only the leader question is a finite choice. Hours are not, and a Yes/No
    pair under "tell me your hours" would be nonsense."""
    monkeypatch.setattr(week_builder, "propose_week_draft", AsyncMock(return_value={
        "status": "clarify",
        "message": "I can't build this week yet — Downtown has no saved hours for every day of the week.",
        "setup_missing": ["operating_hours", "staffing_pattern", "leader_rule"],
    }))

    frames = await _run_turn(monkeypatch, [
        _fake_response(calls=[_fake_call("build_week_schedule", {"source_mode": "auto"})]),
        AssertionError("the turn made a second model call after a schedule clarification"),
    ])
    result = _result(frames)

    assert result["state_updates"].get("huume_choice") in (None, {})


@pytest.mark.asyncio
async def test_seven_day_correction_stages_one_batch_and_executes_nothing(monkeypatch):
    """The reported serial-confirm loop: 28 cancellations + 7 replacement
    shifts must land as ONE staged action carrying the full review, with the
    executor never touched on the stage turn."""
    proposal_id = str(uuid4())
    monkeypatch.setattr(schedule_skill, "propose", AsyncMock(return_value={
        "status": "ready", "proposal_id": proposal_id,
        "pill_text": "📅 Got it. Here's the whole correction, applied together:\n…\nReply **confirm** …",
        "operation_count": 35, "operation_summary": {"cancel": 28, "create": 7},
    }))
    execute = AsyncMock(side_effect=AssertionError("nothing may execute on the stage turn"))
    monkeypatch.setattr(schedule_skill, "execute", execute)
    changes = [
        {"kind": "cancel", "target_date": f"2026-08-{day:02d}", "target_time_hint": f"{hour:02d}:00"}
        for day in range(23, 30) for hour in (6, 10, 14, 18)
    ] + [
        {"kind": "create", "label": "barista", "date": f"2026-08-{day:02d}",
         "start_time": "07:00", "end_time": "15:00"}
        for day in range(23, 30)
    ]

    frames = await _run_turn(
        monkeypatch,
        [_fake_response(calls=[_fake_call("propose_schedule_change", {"changes": changes})]),
         _fake_response(text="Staged the whole correction — confirm to apply it.")],
    )
    result = _result(frames)

    staged = result["state_updates"]["huume_action"]
    assert staged["type"] == "schedule_change"
    assert staged["status"] == "proposed"
    assert staged["proposal_id"] == proposal_id
    assert staged["operation_count"] == 35
    assert staged["operation_summary"] == {"cancel": 28, "create": 7}
    assert staged["confirm_id"]
    assert len(staged["changes"]) == 35
    assert "Here's the whole correction" in staged["pill_text"]
    assert _step_statuses(result) == [("propose_schedule_change", "ok")]
    execute.assert_not_awaited()
