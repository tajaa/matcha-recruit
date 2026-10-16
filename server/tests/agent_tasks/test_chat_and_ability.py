"""Task cards in chat, and the `tasks` ability the assistant uses."""
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.services.matcha_work.agent_runtime import assistant, catalog
from app.matcha.services.matcha_work.agent_runtime.abilities import tasks as ability
from app.matcha.services.matcha_work.agent_runtime.context import RunState
from app.matcha.services.matcha_work.agent_tasks import chat, enqueue, orchestrator, service
from tests.agent_runtime.helpers import FakeConn, context

from ._fixtures import COMPANY, ITEM, TASK, USER, item_row, task_row

ITEM_VIEW = {"id": str(ITEM), "title": "Sunny 1BR", "subtitle": "Mission", "url": "https://apts.test/1",
             "rank": 1, "user_state": "new", "flags": ["unconfirmed:pets"], "images": [{"url": "https://cdn.test/a"}],
             "fields": {"price": {"display": "$3,200/mo", "status": "verified"},
                        "pets": {"display": "Dogs OK", "status": "claimed"}}}
TASK_VIEW = {"id": str(TASK), "playbook": "research", "title": "1bd in SF", "directive": "find a 1bd",
             "status": "done", "phase": "summarize", "progress": {"note": "Found 3"}, "item_count": 3,
             "shown_count": 2, "current_round": 1, "created_at": None, "error": None,
             "plan": {"constraints": [{"label": "Price at most $3,500/mo"}]},
             "rounds": [{"kind": "initial", "status": "done", "summary": {"headline": "One fits", "summary": "x"},
                         "document": None}],
             "items": [ITEM_VIEW]}


def test_cards_and_their_words():
    card = chat.card_view(TASK_VIEW, summary={"headline": "One fits", "counts": {"found": 3}}, top=[ITEM_VIEW])
    assert card["items"][0]["fields"] == {"price": "$3,200/mo", "pets": "Dogs OK"}
    assert card["items"][0]["image"] == "https://cdn.test/a" and card["headline"] == "One fits"
    assert chat.card_text(card) == "Done: 1bd in SF. One fits"
    assert chat.card_text({**card, "event": "started"}).startswith("On it: 1bd in SF.")
    assert chat.card_text({**card, "status": "failed", "note": "Nothing"}) == "Stopped: 1bd in SF. Nothing"
    assert chat.card_text({**card, "status": "waiting"}) == "1bd in SF needs you to go on."
    assert chat.card_text({**card, "status": "running", "note": "Reading"}) == "1bd in SF: Reading"
    assert chat.card_view(task_row(progress='{"note": "Queued"}'))["note"] == "Queued"


@pytest.mark.asyncio
async def test_post_stopped_only_for_a_task_from_a_conversation(monkeypatch):
    from app.matcha.services.matcha_work.project_agent import chat as espresso_chat

    persist = AsyncMock(return_value={"id": "m"})
    monkeypatch.setattr(espresso_chat, "persist_espresso_message", persist)
    channel = uuid4()
    conn = FakeConn().on("FROM mw_agent_tasks WHERE id = $1", task_row(origin_channel_id=channel))
    conn.on("SELECT summary FROM mw_agent_task_rounds", '{"headline": "One fits"}')
    conn.on("rank_band < 9", [item_row()])
    assert await chat.post_stopped(conn, TASK) == {"id": "m"}
    args, kwargs = persist.await_args
    assert args[1:4] == (COMPANY, channel, "Done: 1bd in SF. One fits")
    assert kwargs["metadata"]["kind"] == "agent_task" and kwargs["metadata"]["task"]["items"][0]["title"] == "Sunny 1BR"
    for row in (task_row(), task_row(origin_channel_id=channel, status="cancelled"), None):
        conn.on("FROM mw_agent_tasks WHERE id = $1", row)
        assert await chat.post_stopped(conn, TASK) is None
    conn.on("FROM mw_agent_tasks WHERE id = $1", task_row(origin_channel_id=channel, status="failed"))
    await chat.post_stopped(conn, TASK)
    assert persist.await_args.kwargs["metadata"]["task"]["items"] == []


def test_the_card_shows_the_summarys_picks_in_its_order():
    ranked = [{"id": f"i{n}"} for n in range(8)]
    summary = {"top": [{"item_id": "i6"}, {"item_id": "i2"}, "junk"]}
    assert [i["id"] for i in chat.picks(ranked, summary)] == ["i6", "i2", "i0", "i1", "i3"]
    assert [i["id"] for i in chat.picks(ranked, {})] == ["i0", "i1", "i2", "i3", "i4"]


@pytest.mark.asyncio
async def test_a_stopped_task_posts_its_card(monkeypatch):
    from app.matcha.services.matcha_work.project_agent import chat as espresso_chat

    monkeypatch.setattr(orchestrator.service, "close_round", AsyncMock())
    monkeypatch.setattr(orchestrator.notify, "task_stopped", AsyncMock())
    monkeypatch.setattr(orchestrator.chat, "post_stopped", AsyncMock(return_value={"id": "m"}))
    broadcast = AsyncMock()
    monkeypatch.setattr(espresso_chat, "broadcast_espresso_message", broadcast)
    await orchestrator._stopped("conn", TASK)
    broadcast.assert_awaited_once_with({"id": "m"})
    monkeypatch.setattr(orchestrator.chat, "post_stopped", AsyncMock(side_effect=RuntimeError("down")))
    await orchestrator._stopped("conn", TASK)  # a card that fails never fails the task


def test_the_assistant_gets_ask_form_only_with_tasks():
    tools = assistant.ask_tools([SimpleNamespace(key="web"), SimpleNamespace(key="tasks")])
    assert [t.name for t in tools] == ["ask_user", "ask_form"]
    assert [t.name for t in assistant.ask_tools([SimpleNamespace(key="web")])] == ["ask_user"]
    kind, view, text = assistant.question_message({"question": "Which day?", "options": ["Fri"]})
    assert kind == "ask_user" and view["buttons"][0]["reply"] == "Fri" and text == "Which day?"
    form = {"kind": "ask_form", "question": "Where?", "playbook": "research", "directive": "find a 1bd",
            "title": "", "known": {}, "fields": ["location"], "optional": []}
    kind, view, text = assistant.question_message(form)
    assert kind == "ask_form" and view["form"]["fields"][0]["key"] == "location" and text.startswith("Where?")


def test_the_ability_is_offered_to_tasks_accounts_in_private():
    everything = catalog.build_catalog(fetch_page=None)
    tasks_on = catalog.Situation(private=True, allowed=frozenset({ability.ALLOWANCE}))
    assert "tasks" in [a.key for a in catalog.abilities_for(everything, tasks_on)]
    assert "tasks" not in [a.key for a in catalog.abilities_for(everything, catalog.Situation(private=True))]
    assert "tasks" not in [a.key for a in catalog.abilities_for(
        everything, catalog.Situation(private=False, allowed=frozenset({ability.ALLOWANCE})))]
    prompt = ability._prompt(context())
    assert "research (3 units)" in prompt
    # A choice field names its choices.
    if "job_search (5 units)" in prompt:
        assert "remote (Remote or on-site: one of Any | Remote only | On-site only)" in prompt


def _state():
    state = RunState(started=time.monotonic())
    state.sessions[ability.KEY] = ability.TasksSession()
    return state


def _tool(name):
    return next(t for t in ability.build().tools if t.name == name)


async def _call(name, state, args, ctx=None):
    return await _tool(name).handler(ctx or context(user_id=USER, company_id=COMPANY), state, args, 60.0)


@pytest.mark.asyncio
async def test_reading_tasks_and_their_findings(monkeypatch):
    from app.matcha.services.matcha_work.agent_tasks import allowance

    monkeypatch.setattr(service, "list_tasks", AsyncMock(return_value=[TASK_VIEW]))
    monkeypatch.setattr(service, "get_task", AsyncMock(return_value=TASK_VIEW))
    monkeypatch.setattr(allowance, "task_usage", AsyncMock(return_value={"remaining": 50}))
    state = _state()
    listed = await _call("list_tasks", state, {})
    assert listed.payload["tasks"][0]["note"] == "Found 3" and listed.payload["units"] == {"remaining": 50}
    read = await _call("read_task", state, {"task_id": str(TASK)})
    finding = read.payload["findings"][0]
    assert finding["facts"] == {"price": "$3,200/mo", "pets": "Dogs OK (unconfirmed)"}
    assert read.payload["looking_for"] == ["Price at most $3,500/mo"] and read.payload["latest"]["headline"] == "One fits"
    assert read.provenance == frozenset({"https://apts.test/1"}) and read.payload["next_offset"] is None
    bad = await _call("read_task", state, {"task_id": "nope"})
    assert bad.status == "error" and "id" in bad.payload["error"]
    monkeypatch.setattr(service, "get_task", AsyncMock(side_effect=service.AgentTaskError("Task not found.", 404)))
    assert (await _call("read_task", state, {"task_id": str(uuid4())})).payload == {"error": "Task not found."}
    block, warnings = ability.gate_block("task", {"task_id": str(TASK), "item_ids": [str(ITEM), "x"]}, state)
    assert block["task"]["items"][0]["title"] == "Sunny 1BR" and warnings == ["Dropped a finding this run did not read"]
    assert ability.gate_block("task", {"task_id": "x", "item_ids": []}, state)[0] is None
    assert ability.gate_block("task", "junk", RunState(started=0))[0] is None


@pytest.mark.asyncio
async def test_starting_a_task_from_chat(monkeypatch):
    create = AsyncMock(return_value={**TASK_VIEW, "status": "queued"})
    monkeypatch.setattr(enqueue, "create_task", create)
    state, ctx = _state(), context(user_id=USER, company_id=COMPANY, channel_id=uuid4(), role="individual")
    out = await _call("start_task", state, {"playbook": "research", "directive": "find a 1bd in SF",
                                            "brief": {"location": "SF", "budget_max": "3500"},
                                            "input_ids": [str(ITEM)]}, ctx)
    assert out.payload["started"] is True and str(TASK) in ability.session_of(state).tasks
    user, company, body = create.await_args.args
    assert (user.id, user.role, company) == (USER, "individual", COMPANY)
    assert body.brief == {"location": "SF", "budget_max": 3500.0} and body.input_ids == [ITEM]
    assert create.await_args.kwargs["origin"] == (ctx.channel_id, None)
    again = await _call("start_task", state, {"playbook": "research", "directive": "find a 1bd in SF",
                                              "brief": {"location": "SF", "budget_max": "3500"}}, ctx)
    assert create.await_args.args[2].request_id == body.request_id and again.payload["started"]
    bad = await _call("start_task", state, {"playbook": "research", "directive": "x y z", "brief": {"budget_max": "lots"}})
    assert bad.payload["started"] is False and "budget_max" in bad.payload["invalid"]
    assert (await _call("start_task", state, {"playbook": "nope", "directive": "x", "brief": {}})).status == "error"
    create.side_effect = HTTPException(status_code=429, detail={"code": "task_limit", "message": "No units left."})
    assert (await _call("start_task", state, {"playbook": "research", "directive": "find more", "brief": {}})
            ).payload == {"error": "No units left."}
    create.side_effect = HTTPException(status_code=503, detail="Try later.")
    assert (await _call("start_task", state, {"playbook": "research", "directive": "find it", "brief": {}})
            ).payload == {"error": "Try later."}


@pytest.mark.asyncio
async def test_missing_required_fields_send_the_model_to_ask_form(monkeypatch):
    from dataclasses import replace

    from app.matcha.services.matcha_work.agent_tasks import playbooks
    from app.matcha.services.matcha_work.agent_tasks.playbook import IntakeField

    strict = replace(playbooks.get("research"), intake=(IntakeField(key="location", label="Where",
                                                                     type="location", required=True),))
    monkeypatch.setattr(playbooks, "get", lambda key: strict)
    out = await _call("start_task", _state(), {"playbook": "research", "directive": "find a 1bd", "brief": {}})
    assert out.payload["missing"] == ["location"] and "ask_form" in out.payload["next"]


@pytest.mark.asyncio
async def test_follow_ups_cancel_and_findings(monkeypatch):
    state = _state()
    ability._remember(state, TASK_VIEW, [ITEM_VIEW])
    start_round = AsyncMock(return_value={**TASK_VIEW, "rounds": [{"kind": "refine", "status": "running"}]})
    monkeypatch.setattr(enqueue, "start_round", start_round)
    out = await _call("follow_up_task", state, {"task_id": str(TASK), "kind": "refine", "directive": "only the Mission",
                                                "item_ids": []})
    assert out.payload["round"]["kind"] == "refine" and start_round.await_args.args[2].directive == "only the Mission"
    assert (await _call("follow_up_task", state, {"task_id": "other", "kind": "more", "directive": "",
                                                  "item_ids": []})).payload["error"] == "List or read this task first."
    monkeypatch.setattr(service, "cancel_task", AsyncMock(return_value={**TASK_VIEW, "status": "cancelled"}))
    assert (await _call("cancel_task", state, {"task_id": str(TASK)})).payload["task"]["status"] == "cancelled"
    patch = AsyncMock(return_value={**ITEM_VIEW, "user_state": "saved"})
    monkeypatch.setattr(service, "patch_item", patch)
    out = await _call("update_task_item", state, {"item_id": str(ITEM), "status": "saved", "notes": None})
    assert out.payload["finding"]["user_state"] == "saved" and patch.await_args.kwargs == {"user_state": "saved", "notes": None}
    assert "Read this finding" in (await _call("update_task_item", state, {"item_id": "x", "status": None,
                                                                            "notes": "n"})).payload["error"]
