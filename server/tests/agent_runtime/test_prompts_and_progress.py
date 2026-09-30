from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_card import chat_flow
from app.matcha.services.matcha_work.agent_runtime import chat_progress, prompts

from .helpers import FakeConn


def test_a_confirmation_is_a_clear_yes_or_no_and_nothing_else():
    for text in ("yes", "Yes!", "  y ", "Go ahead.", "do it", "Yes, go ahead", "send it", "confirm"):
        assert prompts.parse_confirmation(text) == "yes", text
    for text in ("no", "No.", "cancel", "Don't", "do not", "never mind", "no thanks"):
        assert prompts.parse_confirmation(text) == "no", text
    for text in ("", "maybe", "ok", "sure", "yes but change the subject first",
                 "I said yes to the other one and I still want that", "not yet", None, 42,
                 "yes " * 20):
        assert prompts.parse_confirmation(text) is None, text


def test_every_button_reply_parses_as_the_answer_it_stands_for():
    view = prompts.confirm_view({"preview": {"title": "Send an email", "lines": [{"label": "To", "value": "x"}]}},
                                ["eve@attacker.test"])
    assert [prompts.parse_confirmation(b["reply"]) for b in view["buttons"]] == ["yes", "no"]
    assert "eve@attacker.test" in view["question"] and view["question"].startswith("Send an email?")
    assert view["action"] == {"title": "Send an email", "lines": [{"label": "To", "value": "x"}]}
    assert prompts.confirm_view({}, [])["question"] == "Go ahead?"
    ask = prompts.ask_view({"question": "Which day?", "options": ["Fri", "Sat"]})
    assert [b["reply"] for b in ask["buttons"]] == ["Fri", "Sat"]
    assert prompts.ask_view({"question": "When?"})["buttons"] == []


def _run(**over):
    base = {"id": uuid4(), "company_id": uuid4(), "channel_id": uuid4(), "requested_by": uuid4(),
            "project_id": None}
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_a_question_is_a_row_and_a_message(monkeypatch):
    prompt_id, message_id = uuid4(), uuid4()
    expires = datetime(2026, 10, 1, tzinfo=timezone.utc)
    conn = FakeConn([("INSERT INTO mw_agent_card_prompts", {"id": prompt_id, "expires_at": expires})])
    persisted = AsyncMock(return_value={"id": str(message_id)})
    monkeypatch.setattr(prompts, "persist_espresso_message", persisted)
    run = _run()
    out = await prompts.ask(conn, run=run, kind=prompts.CONFIRM_ACTION, payload={"tool": "send_email"},
                            view={"question": "Send?"}, content="Send? Reply yes")
    assert out == {"id": str(message_id)}
    insert = conn.ran("INSERT INTO mw_agent_card_prompts")[0]
    assert "NULL" in insert[1]  # no card behind it
    assert insert[2][:6] == (run["company_id"], None, run["id"], run["channel_id"], "confirm_action",
                             run["requested_by"])
    assert insert[2][7] == prompts.CONFIRM_TTL
    metadata = persisted.await_args.kwargs["metadata"]
    assert metadata == {
        "kind": chat_flow.PROMPT_METADATA_KIND, "prompt_id": str(prompt_id),
        "prompt_kind": "confirm_action", "run_id": str(run["id"]),
        "owner_user_id": str(run["requested_by"]), "expires_at": expires.isoformat(),
        "view": {"question": "Send?"},
    }
    assert conn.ran("SET message_id")[0][2] == (prompt_id, message_id)

    project = uuid4()
    await prompts.ask(conn, run=_run(project_id=project), kind=prompts.ASK_USER, payload={},
                      view={}, content="When?")
    assert persisted.await_args.kwargs["metadata"]["project_id"] == str(project)
    assert conn.ran("INSERT INTO mw_agent_card_prompts")[1][2][7] == prompts.ASK_TTL
    # The assistant's replies are recognised as replies to a question by the chat socket.
    assert chat_flow.prompt_reference(metadata) == prompt_id


@pytest.mark.asyncio
async def test_a_message_that_could_not_be_posted_leaves_no_dangling_link(monkeypatch):
    conn = FakeConn([("INSERT INTO mw_agent_card_prompts", {"id": uuid4(), "expires_at": datetime.now(timezone.utc)})])
    monkeypatch.setattr(prompts, "persist_espresso_message", AsyncMock(return_value=None))
    assert await prompts.ask(conn, run=_run(), kind=prompts.ASK_USER, payload={}, view={}, content="") is None
    assert conn.ran("SET message_id") == []


@pytest.mark.asyncio
async def test_a_new_request_answers_an_open_question_and_lets_a_confirmation_lapse():
    channel, owner = uuid4(), uuid4()
    asked, held = uuid4(), uuid4()
    conn = FakeConn([("UPDATE mw_agent_card_prompts", [
        {"id": asked, "channel_id": channel, "kind": "ask_user", "status": "answered"},
        {"id": held, "channel_id": channel, "kind": "confirm_action", "status": "superseded"},
    ])])
    events = await prompts.close_open(conn, channel_id=channel, owner_user_id=owner, as_answered=True)
    assert conn.calls[0][2] == (channel, owner, True)
    assert "owner_user_id = $2" in conn.calls[0][1]
    assert events == [
        {"type": chat_flow.PROMPT_UPDATED_EVENT, "channel_id": str(channel), "prompt_id": str(asked),
         "status": "answered", "answer": "text", "answer_text": "Answered"},
        {"type": chat_flow.PROMPT_UPDATED_EVENT, "channel_id": str(channel), "prompt_id": str(held),
         "status": "superseded", "answer": None, "answer_text": None},
    ]


@pytest.mark.asyncio
async def test_loading_and_claiming():
    prompt_id, channel, owner = uuid4(), uuid4(), uuid4()
    row = {"id": prompt_id, "channel_id": channel, "kind": "confirm_action", "live": True,
           "payload": '{"tool": "send_email"}', "owner_user_id": owner}
    conn = FakeConn([("FROM mw_agent_card_prompts", row), ("SET status = 'answered'", True)])
    loaded = await prompts.load(conn, prompt_id=prompt_id, channel_id=channel)
    assert loaded["payload"] == {"tool": "send_email"}
    assert "kind IN ('ask_user', 'confirm_action')" in conn.calls[0][1]
    pending = await prompts.open_confirmation(conn, channel_id=channel, owner_user_id=owner)
    assert pending["id"] == prompt_id and "expires_at > NOW()" in conn.calls[1][1]
    assert await prompts.claim(conn, loaded, owner, "yes") is True
    assert "status = 'open' AND expires_at > NOW()" in conn.calls[2][1]

    empty = FakeConn()
    assert await prompts.load(empty, prompt_id=prompt_id, channel_id=channel) is None
    assert await prompts.open_confirmation(empty, channel_id=channel, owner_user_id=owner) is None
    assert await prompts.claim(empty, loaded, owner, "yes") is False


@pytest.mark.asyncio
async def test_closed_questions_are_worded_the_assistants_way():
    messages = [
        {"metadata": {"kind": "agent_card_prompt", "prompt_kind": "confirm_action",
                      "prompt_status": "answered", "answer": "yes", "answer_text": "Answered"}},
        {"metadata": '{"kind": "agent_card_prompt", "prompt_kind": "confirm_action", "prompt_status": "answered", "answer": "no"}'},
        {"metadata": {"kind": "agent_card_prompt", "prompt_kind": "ask_user",
                      "prompt_status": "answered", "answer": "text"}},
        {"metadata": {"kind": "agent_card_prompt", "prompt_kind": "show_result",
                      "prompt_status": "answered", "answer": "yes", "answer_text": "Showed the result"}},
        {"metadata": {"kind": "agent_card_prompt", "prompt_kind": "ask_user"}},
        {"metadata": None},
    ]
    out = await prompts.overlay_statuses(None, messages, channel_id=uuid4())
    assert [m["metadata"].get("answer_text") if m["metadata"] else None for m in out] == [
        "Went ahead", "Cancelled", "Answered", "Showed the result", None, None]
    assert prompts.answer_text("ask_user", None) is None


# ── progress ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_progress_goes_out_as_events_and_never_fails_the_run(monkeypatch):
    sent = []

    async def publish(channel_id, event):
        sent.append(event)

    monkeypatch.setattr(chat_progress, "_publish", publish)
    channel, run = uuid4(), uuid4()
    progress = chat_progress.ChatProgress(channel_id=channel, run_id=run)
    await progress.note("Working on it…", force=True)
    await progress.note("dropped: too soon after the last one")
    await progress.step(1, "search", "Searched: desks", "ok")
    await progress.finish("done")
    assert [e["status"] for e in sent] == ["running", "running", "done"]
    assert sent[0] == {"type": "agent_run_progress", "channel_id": str(channel), "run_id": str(run),
                       "status": "running", "note": "Working on it…", "steps": []}
    assert sent[1]["steps"] == [{"seq": 1, "kind": "search", "label": "Searched: desks", "status": "ok"}]
    assert sent[2]["note"] is None

    async def down(channel_id, event):
        raise RuntimeError("redis is down")

    monkeypatch.setattr(chat_progress, "_publish", down)
    await progress.finish("failed", "It took too long.")  # never raises


@pytest.mark.asyncio
async def test_the_event_goes_through_the_existing_chat_bridge(monkeypatch):
    from app.matcha.services.matcha_work import project_task_notifications

    bridge = AsyncMock()
    monkeypatch.setattr(project_task_notifications, "broadcast_channel_event", bridge)
    channel = uuid4()
    await chat_progress._publish(channel, {"type": "agent_run_progress"})
    bridge.assert_awaited_once_with(channel, {"type": "agent_run_progress"})


def test_only_the_latest_steps_are_sent():
    steps = [{"seq": i} for i in range(50)]
    view = chat_progress.progress_view(uuid4(), "running", steps, "note")
    assert len(view["steps"]) == chat_progress.MAX_STEPS and view["steps"][-1] == {"seq": 49}
    run = uuid4()
    assert chat_progress.progress_metadata(run) == {"kind": "agent_progress", "run_id": str(run)}
    assert chat_progress.run_reference({"kind": "agent_progress", "run_id": str(run)}) == run
    assert chat_progress.run_reference({"kind": "agent_progress", "run_id": "nope"}) is None
    assert chat_progress.run_reference({"kind": "agent_card_prompt"}) is None
    assert chat_progress.run_reference(None) is None


@pytest.mark.asyncio
async def test_a_reloaded_chat_reads_the_runs_state_from_its_rows():
    channel, run, other = uuid4(), uuid4(), uuid4()
    conn = FakeConn([
        ("FROM mw_project_agent_runs", [{"id": run, "status": "done", "error": None}]),
        ("FROM mw_project_agent_steps", [
            {"run_id": run, "seq": 1, "kind": "search", "label": "Searched", "status": "ok"},
            {"run_id": run, "seq": 2, "kind": "finish", "label": "Prepared the result", "status": "ok"},
        ]),
    ])
    messages = [
        {"id": 1, "metadata": {"kind": "agent_progress", "run_id": str(run)}},
        {"id": 2, "metadata": '{"kind": "agent_progress", "run_id": "%s"}' % other},
        {"id": 3, "metadata": {"kind": "agent_result"}},
    ]
    out = await chat_progress.overlay_run_progress(conn, messages, channel_id=channel)
    assert out[0]["metadata"]["progress"] == {
        "run_id": str(run), "status": "done", "note": None,
        "steps": [{"seq": 1, "kind": "search", "label": "Searched", "status": "ok"},
                  {"seq": 2, "kind": "finish", "label": "Prepared the result", "status": "ok"}]}
    # A run in another conversation is never read through this one.
    assert out[1] == messages[1] and out[2] == messages[2]
    assert conn.calls[0][2][1] == channel and "kind = 'assistant'" in conn.calls[0][1]

    quiet = FakeConn()
    assert await chat_progress.overlay_run_progress(quiet, [messages[2]], channel_id=channel) == [messages[2]]
    assert quiet.calls == []
    none = FakeConn([("FROM mw_project_agent_runs", [])])
    await chat_progress.overlay_run_progress(none, messages[:1], channel_id=channel)
    assert none.ran("FROM mw_project_agent_steps") == []
