from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.services.matcha_work.agent_card import chat_create, chat_flow
from app.matcha.services.matcha_work.agent_runtime import catalog, chat_entry, chat_progress, enqueue, prompts

from .helpers import FakeConn, connection


def _user():
    return SimpleNamespace(id=uuid4(), role="client", email="ana@example.com")


# ── which mentions are the assistant's ─────────────────────────────────────

def test_assistant_request_leaves_code_talk_to_the_repo_agent():
    for text in ("@espresso where is the order total computed",
                 "@espresso how does our auth flow work",
                 "@espresso find the function that validates tokens"):
        assert chat_entry.assistant_request(text, repo_connected=True) is None, text
        assert chat_entry.assistant_request(text, repo_connected=False) is None, text


def test_a_repo_connected_projects_mention_is_the_repo_agents_unless_it_is_an_errand():
    assert chat_entry.assistant_request("@espresso what changed last week", repo_connected=True) is None
    assert chat_entry.assistant_request(
        "@espresso compare the three venues for the offsite", repo_connected=True,
    ) == "compare the three venues for the offsite"
    assert chat_entry.assistant_request(
        "@espresso   what is the weather   in Lisbon", repo_connected=False,
    ) == "what is the weather in Lisbon"


def test_too_short_to_be_a_request():
    for text in ("@espresso", "@espresso hi", "@espresso yes please"[:13]):
        assert chat_entry.assistant_request(text, repo_connected=False) is None


def test_a_shopping_errand_in_a_project_chat_still_becomes_a_card():
    # The card path is tried first by the mention dispatcher, and claims this.
    text = "@espresso find me organic sweat pants to buy online"
    assert chat_create.errand_request(text) == "find me organic sweat pants to buy online"


def test_refusals_read_as_one_sentence():
    reason = chat_entry._reason
    assert "Pro plan" in reason(HTTPException(403, {"code": "plan_required"}))
    assert "all 30" in reason(HTTPException(429, {"code": "assistant_run_limit", "limit": 30}))
    assert reason(HTTPException(403, {"code": "feature_disabled", "message": "Not switched on."})) == "Not switched on."
    assert "token budget" in reason(HTTPException(402, {"code": "token_budget_exhausted"}))
    assert reason(HTTPException(409, enqueue.STILL_WORKING)) == enqueue.STILL_WORKING
    assert reason(HTTPException(429, {"message": "Slow down."})) == "Slow down."
    assert reason(HTTPException(418, "")) == "Please try again in a moment."


# ── starting a run ─────────────────────────────────────────────────────────

@pytest.fixture
def wired(monkeypatch):
    posted = []

    async def post(company_id, channel_id, content, *, metadata=None):
        posted.append((content, metadata))

    monkeypatch.setattr(chat_entry, "post_as_espresso", post)
    monkeypatch.setattr(enqueue, "preflight", AsyncMock())
    queued = AsyncMock(return_value={"run_id": str(uuid4()), "status": "queued"})
    monkeypatch.setattr(enqueue, "enqueue_assistant_run", queued)
    monkeypatch.setattr(chat_entry, "ability_keys", AsyncMock(return_value=["web", "shopping"]))
    conn = FakeConn()
    monkeypatch.setattr(chat_entry, "get_connection", connection(conn))
    broadcast = AsyncMock()
    monkeypatch.setattr(chat_flow, "broadcast_prompt_updates", broadcast)
    monkeypatch.setattr(chat_entry, "broadcast_espresso_message", AsyncMock())
    persisted = []

    async def persist(conn_, company_id, channel_id, text, *, metadata=None):
        persisted.append(text)
        return {"id": str(uuid4()), "content": text}

    monkeypatch.setattr(chat_entry, "persist_espresso_message", persist)
    return SimpleNamespace(posted=posted, queued=queued, conn=conn, broadcast=broadcast, persisted=persisted)


def _message(user, **over):
    base = dict(channel_id=uuid4(), company_id=uuid4(), user=user, content="find a standing desk",
                message_id=uuid4(), surface="assistant")
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_a_plain_message_starts_a_run_and_is_acknowledged(wired):
    user = _user()
    message = _message(user, content="  find   a standing desk ")
    assert await chat_entry.handle_message(**message) is True
    kwargs = wired.queued.await_args.kwargs
    assert kwargs["prompt"] == "find a standing desk" and kwargs["surface"] == "assistant"
    assert kwargs["trigger_message_id"] == message["message_id"] and kwargs["skip_preflight"] is True
    assert kwargs["abilities"] == ["web", "shopping"] and kwargs["resume_prompt_id"] is None
    content, metadata = wired.posted[0]
    assert content == chat_entry.ON_IT
    assert metadata == chat_progress.progress_metadata(wired.queued.return_value["run_id"])
    # Whatever the person had left open here is moved past.
    closed = wired.conn.ran("UPDATE mw_agent_card_prompts")[0]
    assert closed[2] == (message["channel_id"], user.id, True)


@pytest.mark.asyncio
async def test_a_mention_is_stripped_and_an_empty_one_is_asked_what_it_wants(wired):
    await chat_entry.handle_message(**_message(_user(), content="@espresso compare venues for friday",
                                               surface="project_chat", project_id=uuid4()))
    assert wired.queued.await_args.kwargs["prompt"] == "compare venues for friday"
    assert wired.queued.await_args.kwargs["surface"] == "project_chat"
    wired.queued.reset_mock()
    await chat_entry.handle_message(**_message(_user(), content="@espresso   "))
    assert wired.posted[-1][0] == chat_entry.NOTHING_TO_ASK
    wired.queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_refusal_is_posted_and_no_run_row_exists(wired):
    enqueue.preflight.side_effect = HTTPException(403, {"code": "plan_required"})
    assert await chat_entry.handle_message(**_message(_user())) is True
    wired.queued.assert_not_awaited()
    assert wired.posted == [("The Espresso assistant needs the Pro plan.", None)]

    enqueue.preflight.side_effect = None
    wired.queued.side_effect = HTTPException(409, enqueue.STILL_WORKING)
    await chat_entry.handle_message(**_message(_user()))
    assert wired.posted[-1] == (enqueue.STILL_WORKING, None)


@pytest.mark.asyncio
async def test_a_message_delivered_twice_is_acknowledged_once(wired):
    wired.queued.return_value = {"run_id": None, "status": "duplicate"}
    assert await chat_entry.handle_message(**_message(_user())) is True
    assert wired.posted == []


@pytest.mark.asyncio
async def test_anything_going_wrong_is_said_in_chat_not_raised(wired, monkeypatch):
    monkeypatch.setattr(chat_entry, "ability_keys", AsyncMock(side_effect=RuntimeError("boom")))
    assert await chat_entry.handle_message(**_message(_user())) is True
    assert "Something went wrong" in wired.posted[-1][0]

    async def broken_post(*_a, **_k):
        raise RuntimeError("chat is down too")

    monkeypatch.setattr(chat_entry, "post_as_espresso", broken_post)
    assert await chat_entry.handle_message(**_message(_user())) is True


# ── answering a question ───────────────────────────────────────────────────

def _prompt(owner, kind="confirm_action", **over):
    base = {"id": uuid4(), "kind": kind, "owner_user_id": owner, "live": True, "company_id": uuid4(),
            "channel_id": uuid4(), "message_id": uuid4(), "run_id": uuid4(), "project_id": None,
            "payload": {"tool": "send_email"}}
    base.update(over)
    return base


def _script(wired, prompt, *, claimed=True, surface="assistant"):
    wired.conn.on("SET status = 'answered'", claimed)
    wired.conn.on("SELECT surface FROM mw_project_agent_runs", surface)
    wired.conn.on("FROM mw_agent_card_prompts", {**prompt})


@pytest.mark.asyncio
async def test_a_yes_runs_the_frozen_action_and_a_no_drops_it(wired):
    user = _user()
    prompt = _prompt(user.id)
    _script(wired, prompt)
    message = _message(user, content="yes", reply_prompt_id=prompt["id"], channel_id=prompt["channel_id"])
    assert await chat_entry.handle_message(**message) is True
    kwargs = wired.queued.await_args.kwargs
    assert kwargs["resume_prompt_id"] == prompt["id"] and kwargs["prompt"] == "Yes, go ahead."
    assert kwargs["trigger_message_id"] == message["message_id"]
    event = wired.broadcast.await_args.args[0][0]
    assert event["status"] == "answered" and event["answer"] == "yes" and event["answer_text"] == "Went ahead"

    wired.queued.reset_mock()
    await chat_entry.handle_message(**{**message, "content": "No, cancel", "message_id": uuid4()})
    wired.queued.assert_not_awaited()
    assert wired.persisted[-1] == chat_entry.CANCELLED


@pytest.mark.asyncio
async def test_anything_but_a_clear_yes_or_no_leaves_the_question_open(wired):
    user = _user()
    prompt = _prompt(user.id)
    _script(wired, prompt)
    await chat_entry.handle_message(**_message(
        user, content="yes but change the subject", reply_prompt_id=prompt["id"],
        channel_id=prompt["channel_id"]))
    wired.queued.assert_not_awaited()
    assert wired.persisted == [prompts.CONFIRM_HINT]
    assert wired.conn.ran("SET status = 'answered'") == []


@pytest.mark.asyncio
async def test_only_the_asker_can_answer(wired):
    owner = uuid4()
    prompt = _prompt(owner)
    _script(wired, prompt)
    await chat_entry.handle_message(**_message(
        _user(), content="yes", reply_prompt_id=prompt["id"], channel_id=prompt["channel_id"]))
    wired.queued.assert_not_awaited()
    assert wired.persisted == [chat_entry.NOT_YOURS]
    assert wired.conn.ran("SET status = 'answered'") == []


@pytest.mark.asyncio
async def test_a_closed_or_already_claimed_question_is_not_answered_twice(wired):
    user = _user()
    expired = _prompt(user.id, live=False)
    _script(wired, expired)
    await chat_entry.handle_message(**_message(
        user, content="yes", reply_prompt_id=expired["id"], channel_id=expired["channel_id"]))
    raced = _prompt(user.id)
    _script(wired, raced, claimed=None)
    await chat_entry.handle_message(**_message(
        user, content="yes", reply_prompt_id=raced["id"], channel_id=raced["channel_id"]))
    asked = _prompt(user.id, kind="ask_user")
    _script(wired, asked, claimed=None)
    await chat_entry.handle_message(**_message(
        user, content="Friday", reply_prompt_id=asked["id"], channel_id=asked["channel_id"]))
    assert wired.persisted == [chat_entry.CLOSED] * 3
    wired.queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_threaded_reply_to_a_question_starts_the_next_run(wired):
    user = _user()
    project = uuid4()
    prompt = _prompt(user.id, kind="ask_user", project_id=project)
    _script(wired, prompt, surface="project_chat")
    # Reached the way a project chat reaches it: by the question's id alone.
    handled = await chat_entry.handle_prompt_reply(
        channel_id=prompt["channel_id"], user=user, content="Friday at 7", prompt_id=prompt["id"],
        message_id=uuid4(),
    )
    assert handled is True
    kwargs = wired.queued.await_args.kwargs
    assert kwargs["prompt"] == "Friday at 7" and kwargs["surface"] == "project_chat"
    assert kwargs["project_id"] == project and kwargs["resume_prompt_id"] is None
    assert wired.broadcast.await_args.args[0][0]["answer_text"] == "Answered"


@pytest.mark.asyncio
async def test_a_reply_to_an_agent_card_question_is_not_the_assistants(wired):
    wired.conn.on("FROM mw_agent_card_prompts", None)
    handled = await chat_entry.handle_prompt_reply(
        channel_id=uuid4(), user=_user(), content="yes", prompt_id=uuid4())
    assert handled is None
    # ...so a message replying to one falls through to a fresh request.
    await chat_entry.handle_message(**_message(_user(), content="book a table", reply_prompt_id=uuid4()))
    assert wired.queued.await_args.kwargs["prompt"] == "book a table"


@pytest.mark.asyncio
async def test_the_reply_message_is_found_when_the_caller_did_not_have_its_id(wired):
    user = _user()
    prompt = _prompt(user.id, kind="ask_user")
    found = uuid4()
    wired.conn.on("SET status = 'answered'", True)
    wired.conn.on("SELECT surface FROM mw_project_agent_runs", None)
    wired.conn.on("FROM channel_messages", found)
    assert await chat_entry.answer_loaded_prompt(
        prompt=prompt, channel_id=prompt["channel_id"], user=user, content="Friday") is True
    assert wired.queued.await_args.kwargs["trigger_message_id"] == found
    assert wired.queued.await_args.kwargs["surface"] == "assistant"
    lookup = wired.conn.ran("FROM channel_messages")[0]
    assert lookup[2] == (prompt["channel_id"], user.id, prompt["message_id"])

    wired.queued.reset_mock()
    wired.conn.on("FROM channel_messages", None)
    assert await chat_entry.answer_loaded_prompt(
        prompt=prompt, channel_id=prompt["channel_id"], user=user, content="Friday") is True
    wired.queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_plain_yes_answers_the_persons_own_open_confirmation(wired):
    user = _user()
    prompt = _prompt(user.id)
    wired.conn.on("SET status = 'answered'", True)
    wired.conn.on("kind = 'confirm_action'", {**prompt})
    await chat_entry.handle_message(**_message(user, content="Yes", channel_id=prompt["channel_id"]))
    assert wired.queued.await_args.kwargs["resume_prompt_id"] == prompt["id"]
    lookup = wired.conn.ran("kind = 'confirm_action'")[0]
    assert lookup[2] == (prompt["channel_id"], user.id)
    # It was answered, not moved past.
    assert wired.conn.ran("WHERE channel_id = $1 AND owner_user_id = $2 AND status = 'open' AND kind IN") == []


@pytest.mark.asyncio
async def test_a_plain_yes_with_nothing_open_is_just_a_message(wired):
    await chat_entry.handle_message(**_message(_user(), content="yes"))
    assert wired.queued.await_args.kwargs["prompt"] == "yes"
    assert wired.queued.await_args.kwargs["resume_prompt_id"] is None


# ── which abilities a run gets ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_project_chat_gets_no_private_ability_whatever_is_switched_on(monkeypatch):
    from app.matcha.services.matcha_work import gmail_service
    from app.matcha.services.matcha_work.agent_runtime import conversation, grants

    conn = FakeConn()
    monkeypatch.setattr(chat_entry, "get_connection", connection(conn))
    private = AsyncMock(return_value=True)
    monkeypatch.setattr(conversation, "is_private_conversation", private)
    loaded = AsyncMock(return_value={"email": {}, "calendar": {}})
    monkeypatch.setattr(grants, "load_grants", loaded)

    class Gmail:
        def __init__(self, user_id):
            self.is_configured = True
            self.granted_scopes = frozenset(gmail_service.GMAIL_SCOPES)

        async def load_token(self):
            return None

    monkeypatch.setattr(gmail_service, "GmailService", Gmail)
    user = _user()
    assert await chat_entry.ability_keys(user, uuid4(), uuid4(), "project_chat") == ["web", "shopping"]
    private.assert_not_awaited()
    loaded.assert_not_awaited()
    keys = await chat_entry.ability_keys(user, uuid4(), uuid4(), "assistant")
    assert keys == ["web", "shopping", "email", "calendar"]

    private.return_value = False  # someone else got into the conversation
    assert await chat_entry.ability_keys(user, uuid4(), uuid4(), "assistant") == ["web", "shopping"]
    assert isinstance(await chat_entry._situation(user, uuid4(), uuid4(), "assistant"), catalog.Situation)
