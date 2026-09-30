import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_runtime import chat_entry
from app.matcha.services.matcha_work.project_agent import chat
from app.werk.routes import channels_ws

from tests.agent_runtime.helpers import FakeConn, connection


def _user():
    return SimpleNamespace(id=uuid4(), role="client", email="ana@example.com")


@pytest.fixture
def wired(monkeypatch):
    handled = AsyncMock(return_value=True)
    monkeypatch.setattr(chat_entry, "handle_message", handled)
    posted = AsyncMock()
    monkeypatch.setattr(chat, "post_as_espresso", posted)
    company = uuid4()
    conn = FakeConn([("FROM channels", company)])
    monkeypatch.setattr(channels_ws, "get_connection", connection(conn))
    return SimpleNamespace(handled=handled, posted=posted, conn=conn, company=company)


@pytest.mark.asyncio
async def test_a_plain_message_starts_a_run_without_a_mention(wired):
    user, channel, message = _user(), uuid4(), uuid4()
    await channels_ws._bg_assistant_message(str(channel), user, "find a standing desk", message, None, False)
    kwargs = wired.handled.await_args.kwargs
    assert kwargs == dict(channel_id=channel, company_id=wired.company, user=user,
                          content="find a standing desk", message_id=message, surface="assistant",
                          reply_prompt_id=None)
    wired.posted.assert_not_awaited()
    # The channel is looked up as THIS person's conversation, not just by id.
    lookup = wired.conn.ran("FROM channels")[0]
    assert "assistant_user_id = $2" in lookup[1] and lookup[2] == (channel, user.id)


@pytest.mark.asyncio
async def test_a_reply_to_a_question_carries_the_question(wired):
    prompt = uuid4()
    await channels_ws._bg_assistant_message(str(uuid4()), _user(), "yes", uuid4(), prompt, False)
    assert wired.handled.await_args.kwargs["reply_prompt_id"] == prompt


@pytest.mark.asyncio
async def test_a_channel_that_is_not_this_persons_conversation_starts_nothing(wired):
    wired.conn.on("FROM channels", None)
    await channels_ws._bg_assistant_message(str(uuid4()), _user(), "find a desk", uuid4(), None, False)
    wired.handled.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_removed_card_number_is_said_and_the_message_still_handled(wired):
    await channels_ws._bg_assistant_message(
        str(uuid4()), _user(), "use [card number removed]", uuid4(), None, True)
    assert "removed a card number" in wired.posted.await_args.args[2]
    wired.handled.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failure_never_reaches_the_socket(wired):
    wired.handled.side_effect = RuntimeError("boom")
    await channels_ws._bg_assistant_message(str(uuid4()), _user(), "find a desk", uuid4(), None, False)


def test_a_card_number_is_removed_before_storage():
    content, removed = channels_ws._assistant_redaction("pay with 4242 4242 4242 4242 please")
    assert removed and "4242" not in content and "[card number removed]" in content
    assert channels_ws._assistant_redaction("table for 4 at 19:00 on 2026-10-02") == (
        "table for 4 at 19:00 on 2026-10-02", False)
    assert channels_ws._assistant_redaction("") == ("", False)
    assert channels_ws._assistant_redaction(None) == (None, False)


def _send_path() -> str:
    source = inspect.getsource(channels_ws)
    start = source.index("is_assistant = access.scope is ChannelScope.ASSISTANT")
    end = source.index("await manager.broadcast_message(room_key, {", start)
    return source[start:end]


def test_no_other_dispatcher_fires_in_the_assistant_scope():
    """Every dispatcher after the assistant's is gated on `dispatch_new`, which
    is False in a private conversation."""
    path = _send_path()
    branch = path[path.index("if is_assistant:\n                                # A private conversation"):]
    assert "dispatch_new = False" in branch and "dispatch_new = is_new_message" in branch
    chain = branch[branch.index("dispatch_new = is_new_message"):]
    dispatchers = [line.strip() for line in chain.splitlines() if "_spawn_bg(_bg_" in line]
    assert len(dispatchers) >= 6, dispatchers
    # Nothing in the chain is still gated on the raw flag.
    after = chain.split("dispatch_new = is_new_message", 1)[1]
    assert "is_new_message" not in after
    assert chain.count("dispatch_new") >= 6


def test_redaction_in_the_assistant_scope_does_not_depend_on_an_open_question():
    path = _send_path()
    assert path.index("_assistant_redaction(content)") < path.index("_agent_card_redaction(")
    assert "if is_assistant:" in path[: path.index("_assistant_redaction(content)")]


def test_the_mention_dispatcher_tries_the_card_then_the_assistant_then_the_repo_agent():
    source = inspect.getsource(channels_ws._bg_dispatch_espresso_mention)
    card = source.index("handle_agent_card_mention(")
    ours = source.index("chat_entry.assistant_request(")
    repo = source.index('if not project["github_repo"]')
    assert card < ours < repo
    assert "assistant_available(" in source[card:ours]
    assert 'surface="project_chat"' in source[ours:repo]
