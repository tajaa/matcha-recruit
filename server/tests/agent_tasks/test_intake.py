"""Asking for a task's details: values, the form, and submitting it."""
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.matcha_work.agent_tasks import FormAnswer
from app.matcha.services.matcha_work.agent_tasks import intake, playbooks
from app.matcha.services.matcha_work.agent_tasks.playbook import IntakeField
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import COMPANY, TASK, USER

R = playbooks.get("research")
F = lambda key, type_, **kw: IntakeField(key=key, label=key.title(), type=type_, **kw)  # noqa: E731


def test_clean_value_by_type():
    c = intake.clean_value
    assert c(F("a", "text"), "  hi \n there ") == "hi there" and c(F("a", "text"), "") is None
    assert c(F("a", "money"), "$3,500") == 3500.0 and c(F("a", "number"), 2) == 2.0
    assert c(F("a", "date"), "2026-11-01T10:00") == "2026-11-01" and c(F("a", "time"), "7:05") == "07:05"
    assert c(F("a", "select", options=("x", "y")), "y") == "y"
    assert c(F("a", "multi_select", options=("x", "y")), ["y", "y"]) == ["y"]
    assert c(F("a", "boolean"), "Yes") is True and c(F("a", "boolean"), False) is False
    assert c(F("a", "list"), "dogs, Dogs, parking") == ["dogs", "parking"] and c(F("a", "list"), [" "]) is None
    # Semicolons (or new lines) separate items when there are any, so a place
    # keeps its comma; an array's items are kept whole unless they hold one.
    assert c(F("a", "list"), "New York, NY; Remote") == ["New York, NY", "Remote"]
    assert c(F("a", "list"), ["VP of Operations; COO"]) == ["VP of Operations", "COO"]
    assert c(F("a", "list"), ["New York, NY", "Remote"]) == ["New York, NY", "Remote"]
    assert c(F("a", "list"), "Austin\nDenver") == ["Austin", "Denver"]
    # A wrong choice names the right ones, so the model can fix it.
    with pytest.raises(ValueError, match="should be one of: Any, Remote only"):
        c(F("a", "select", options=("Any", "Remote only")), "Either")
    with pytest.raises(ValueError, match="takes only: x"):
        c(F("a", "multi_select", options=("x",)), ["z"])
    for spec, bad in ((F("a", "text"), {"x": 1}), (F("a", "money"), True), (F("a", "money"), "lots"),
                      (F("a", "money"), -1), (F("a", "date"), "soon"), (F("a", "time"), "25:00"),
                      (F("a", "select", options=("x",)), "z"), (F("a", "multi_select", options=("x",)), ["z"]),
                      (F("a", "boolean"), "maybe"), (F("a", "file", accept=("image",)), "x"),
                      (F("a", "color"), "red")):
        with pytest.raises(ValueError):
            c(spec, bad)


def test_clean_values_names_what_is_wrong():
    clean, errors = intake.clean_values(R, {"location": "SF", "budget_max": "lots", "nope": 1,
                                            "reference_files": ["x"]})
    assert clean == {"location": "SF"} and errors == {"budget_max": "Budget (max) should be a number."}


def test_the_form_comes_from_the_playbook():
    form = intake.build_form(R, directive="  find a 1bd ", title="1bd", known={"location": "SF", "made_up": 1},
                             missing=["budget_max", "needed_by", "nope"], note="", consent_needed=False)
    assert form["fields"] == ["budget_max", "needed_by"]  # named, including a `never` field
    assert form["optional"] == ["must_haves", "nice_to_haves", "avoid"]
    assert form["known"] == {"location": "SF"} and form["directive"] == "find a 1bd"
    assert form["question"] == "A few details for this research task" and form["consent"] is None
    required = replace(R, intake=(F("where", "location", required=True), F("when", "date", ask="always"),
                                  F("why", "text", ask="never")))
    form = intake.build_form(required, directive="x y z", title="", known={"when": "2026-11-01"},
                             missing=[], note="Two things", consent_needed=True)
    assert form["fields"] == ["where", "when"] and form["optional"] == [] and form["consent"] is None
    nothing = replace(R, intake=(F("where", "location"),))
    with pytest.raises(ValueError):
        intake.build_form(nothing, directive="x y z", title="", known={"where": "SF"}, missing=[], note="",
                          consent_needed=False)


def test_views_show_fields_known_values_and_consent():
    payload = intake.build_form(R, directive="find a 1bd", title="1bd", known={"budget_max": 3500, "must_haves": ["dogs"]},
                                missing=["location"], note="Where should I look?", consent_needed=False)
    view = intake.form_view({**payload, "consent": "jobs"})
    form = view["form"]
    assert view["question"] == "Where should I look?" and view["buttons"] == []
    assert [f["key"] for f in form["fields"]] == ["location", "nice_to_haves", "avoid"]
    assert form["fields"][1]["optional"] is True and form["units"] == 3 and form["submit_label"] == "Start"
    assert {k["key"]: k["shown"] for k in form["known"]} == {"budget_max": "$3,500", "must_haves": "dogs"}
    assert form["consent"]["version"] == "jobs-2"
    text = intake.form_text(payload)
    assert text.startswith("Where should I look?") and "Where; Nice to have (optional)" in text
    assert intake._shown(F("a", "boolean"), True) == "Yes" and intake._shown(F("a", "text"), "x") == "x"
    assert intake.form_view({"playbook": "gone"})["form"]["fields"] == []


def test_the_ask_form_tool_checks_what_the_model_sent():
    tool = intake.ask_form_tool()
    assert tool.effect == "ask" and tool.parameters["properties"]["playbook"]["enum"] == [
        "apartments", "job_search", "places", "products", "research"]
    ctx = SimpleNamespace(grants={})
    with pytest.raises(ValueError):
        tool.parse_ask(ctx, None, {"playbook": "nope", "directive": "find it"})
    with pytest.raises(ValueError):
        tool.parse_ask(ctx, None, {"playbook": "research", "directive": "x"})
    form = tool.parse_ask(ctx, None, {"playbook": "research", "directive": "find a 1bd in SF", "known": "bad",
                                      "missing": "bad", "note": "Where?"})
    assert form["kind"] == "ask_form" and form["fields"] == [] and form["optional"]


@pytest.fixture
def answering(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(intake, "connection_or_direct", connection(conn))
    create = AsyncMock(return_value={"id": str(TASK), "title": "1bd", "status": "queued", "progress": {"note": "Queued."},
                                     "playbook": "research"})
    monkeypatch.setattr(intake.enqueue, "create_task", create)
    from app.matcha.services.matcha_work.agent_card import chat_flow
    from app.matcha.services.matcha_work.project_agent import chat as espresso_chat

    monkeypatch.setattr(chat_flow, "broadcast_prompt_updates", AsyncMock())
    monkeypatch.setattr(espresso_chat, "broadcast_espresso_message", AsyncMock())
    monkeypatch.setattr(intake.chat, "post_card", AsyncMock(return_value={"id": "m1"}))
    return SimpleNamespace(conn=conn, create=create, chat_flow=chat_flow, espresso_chat=espresso_chat)


def _prompt(**over):
    payload = {"kind": "ask_form", "playbook": "research", "directive": "find a 1bd in SF", "title": "1bd",
               "known": {"location": "SF"}, "fields": ["budget_max"], "optional": []}
    return {"id": uuid4(), "owner_user_id": USER, "company_id": COMPANY, "channel_id": uuid4(),
            "message_id": uuid4(), "kind": "ask_form", "status": "open", "live": True, "agent_task_id": None,
            "payload": json.dumps(payload), **over}


ME = SimpleNamespace(id=USER, role="client")


@pytest.mark.asyncio
async def test_submitting_starts_the_task_and_closes_the_form(answering):
    prompt = _prompt()
    answering.conn.on("FROM mw_agent_card_prompts WHERE id = $1 AND kind = 'ask_form'", prompt)
    answering.conn.on("SET status = 'answered', answer = $2", True)
    task = await intake.answer_form(ME, prompt["id"], FormAnswer(values={"budget_max": "3500"}))
    assert task["id"] == str(TASK)
    body = answering.create.await_args.args[2]
    assert body.request_id == prompt["id"] and body.brief == {"location": "SF", "budget_max": 3500.0}
    assert answering.create.await_args.kwargs["origin"] == (prompt["channel_id"], prompt["message_id"])
    assert answering.conn.ran("agent_task_id = $4")[0][2][1:] == ("form", USER, TASK)
    answering.chat_flow.broadcast_prompt_updates.assert_awaited_once()
    answering.espresso_chat.broadcast_espresso_message.assert_awaited_once_with({"id": "m1"})
    # Someone else's submit got there first: no second card.
    answering.conn.on("SET status = 'answered', answer = $2", None)
    await intake.answer_form(ME, prompt["id"], FormAnswer(values={"budget_max": 3500}))
    assert answering.espresso_chat.broadcast_espresso_message.await_count == 1


@pytest.mark.asyncio
async def test_refusals_and_a_retry(answering, monkeypatch):
    q = "FROM mw_agent_card_prompts WHERE id = $1 AND kind = 'ask_form'"
    for prompt, code in ((None, 404), (_prompt(owner_user_id=uuid4()), 404), (_prompt(live=False), 409),
                         (_prompt(payload=json.dumps({"playbook": "gone"})), 409)):
        answering.conn.on(q, prompt)
        with pytest.raises(HTTPException) as exc:
            await intake.answer_form(ME, uuid4(), FormAnswer())
        assert exc.value.status_code == code
    answering.conn.on(q, _prompt())
    with pytest.raises(HTTPException) as exc:
        await intake.answer_form(ME, uuid4(), FormAnswer(values={"budget_max": "a lot"}))
    assert exc.value.detail["errors"] == {"budget_max": "Budget (max) should be a number."}
    monkeypatch.setattr(intake.playbooks, "get", lambda key: replace(R, intake=(F("where", "location", required=True),)))
    with pytest.raises(HTTPException) as exc:
        await intake.answer_form(ME, uuid4(), FormAnswer())
    assert exc.value.detail["errors"] == {"where": "Where is needed."}
    get_task = AsyncMock(return_value={"id": "same"})
    monkeypatch.setattr(intake.service, "get_task", get_task)
    answering.conn.on(q, _prompt(agent_task_id=TASK, live=False))
    assert await intake.answer_form(ME, uuid4(), FormAnswer()) == {"id": "same"}
    answering.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_files_must_fit_the_file_fields():
    conn = FakeConn()
    await intake._check_files(conn, R, USER, [])
    files = [uuid4(), uuid4()]
    with pytest.raises(HTTPException) as exc:
        await intake._check_files(conn, replace(R, intake=(F("where", "location"),)), USER, files)
    assert "no files" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        await intake._check_files(conn, R, USER, [uuid4() for _ in range(4)])
    assert "At most 3" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        await intake._check_files(conn, R, USER, files)
    assert exc.value.status_code == 404
    conn.on("FROM mw_agent_inputs", [{"id": files[0], "kind": "image", "size_bytes": 10},
                                     {"id": files[1], "kind": "audio", "size_bytes": 10}])
    with pytest.raises(HTTPException) as exc:
        await intake._check_files(conn, R, USER, files)
    assert "kind" in exc.value.detail
    conn.on("FROM mw_agent_inputs", [{"id": files[0], "kind": "image", "size_bytes": 10},
                                     {"id": files[1], "kind": "document", "size_bytes": 11 * 1024 * 1024}])
    with pytest.raises(HTTPException) as exc:
        await intake._check_files(conn, R, USER, files)
    assert "too large" in exc.value.detail
    conn.on("FROM mw_agent_inputs", [{"id": files[0], "kind": "image", "size_bytes": 10},
                                     {"id": files[1], "kind": "document", "size_bytes": 10}])
    await intake._check_files(conn, R, USER, files)
