"""Scope contract and same-thread context replay; all I/O is in memory.

The scripted model checks the instructions and context it receives, not LLM
compliance. The real-model reproduction is recorded in docs/reviews/espresso-answer-scope.md.
"""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.huume.luna_client import text_item
from app.matcha.services.matcha_work.agent_runtime import history, prompt, result, runner
from app.matcha.services.matcha_work.agent_runtime.abilities import calendar, email
from app.matcha.services.matcha_work.agent_runtime.context import FrozenAction
from app.matcha.services.matcha_work.gmail_service import SCOPE_GMAIL_COMPOSE, SCOPE_GMAIL_READONLY

from .helpers import FakeClient, FakeConn, call, context, response, wire_store

ADD = "Add a dentist appointment to my Espresso calendar on October 20, 2026 from 3 to 4 PM."
EMAIL = "What did I say in the email I sent Dana about the lease renewal?"
EVENT = {
    "id": "7a2b3c4d-0000-4000-8000-000000000001", "title": "Dentist appointment",
    "start": "2026-10-20T15:00:00-07:00", "end": "2026-10-20T16:00:00-07:00",
    "all_day": False,
}
MAIL = {
    "id": "sent-lease", "thread_id": "lease-thread", "from": "me@example.com",
    "to": "dana@example.org", "subject": "Lease renewal", "date": "2026-09-28",
    "body": "I confirmed renewal for one year at $2,400 per month.",
    "snippet": "Renewal for one year at $2,400 per month.",
}


def _row(sender, content, *, bot=False, run_id=None, kind=None):
    return {
        "id": uuid4(), "sender_id": sender, "content": content, "from_espresso": bot,
        "sender_name": "Me", "metadata_kind": kind, "run_id": str(run_id) if run_id else None,
    }


class ScopeClient(FakeClient):
    async def create_response(self, **kwargs):
        # Pin the model contract on every call, including after tool results.
        instructions = kwargs["instructions"]
        assert "The latest user message is the active request" in instructions
        assert "Do not repeat, re-check or resume completed work" in instructions
        assert "Keep tool calls and every part of the final answer focused on the current request" in instructions
        assert "including unsolicited confirmations or corrections of it" in instructions
        assert "Use them to understand references and relevant follow-ups" in instructions
        assert "unless the current request asks for it or depends on it" in instructions
        assert "so their absence is not evidence they did not happen" in instructions
        return await super().create_response(**kwargs)


async def _run(ctx, abilities, client, replay=()):
    return await runner.run_agent(
        ctx, client=client, abilities=abilities,
        instructions=prompt.build_system_prompt(ctx, abilities),
        first_input=[*replay, text_item("user", ctx.ask)],
        contract=runner.ResultContract(
            finish=result.finish_tool(abilities),
            normalize=lambda args, state: result.normalize(args, state, abilities),
        ),
    )


@pytest.mark.asyncio
async def test_calendar_then_email_replays_history_with_current_request_scope(monkeypatch):
    wire_store(monkeypatch)
    store, gmail = AsyncMock(), AsyncMock()
    store.create_event.return_value = EVENT
    gmail.search.return_value = [MAIL]
    gmail.get_message.return_value = MAIL
    abilities = [
        calendar.build(calendar_factory=lambda _: None, espresso_store=store),
        email.build(gmail_factory=lambda _: gmail),
    ]
    first = context(
        ask=ADD, channel_id=uuid4(), timezone="America/Los_Angeles", store_responses=False,
        granted_scopes=frozenset({SCOPE_GMAIL_READONLY, SCOPE_GMAIL_COMPOSE}),
    )
    client = ScopeClient([
        response(call("add_espresso_event", {"title": EVENT["title"], "start": EVENT["start"],
                                            "end": EVENT["end"]})),
        response(call("finish", {"headline": "Dentist appointment added", "summary": "October 20, 3–4 PM.",
                                 "blocks": [{"type": "events", "event_ids": [EVENT["id"]]}]})),
    ])
    added = await _run(first, abilities, client)
    assert added.result["blocks"][0]["items"][0]["event_id"] == EVENT["id"]
    store.create_event.assert_awaited_once()

    trigger = _row(first.user_id, EMAIL)
    rows = [
        trigger,
        _row(uuid4(), "Dentist appointment added\n\nOctober 20, 3–4 PM.", bot=True,
             run_id=first.run_id, kind="agent_result"),
        _row(first.user_id, ADD),
    ]
    replay, own = await history.build_history(
        FakeConn([("FROM channel_messages", rows)]), channel_id=first.channel_id,
        requester_id=first.user_id, trigger_message_id=trigger["id"],
    )
    assert own == (ADD, EMAIL)
    assert replay[0]["content"][0]["text"] == ADD
    assert "Dentist appointment added" in replay[1]["content"][0]["text"]
    second = context(
        ask=EMAIL, channel_id=first.channel_id, user_id=first.user_id, company_id=first.company_id,
        store_responses=False, granted_scopes=first.granted_scopes,
    )
    client = ScopeClient([
        response(call("search_email", {"query": "in:sent to:dana@example.org subject:lease"})),
        response(call("read_email", {"message_id": MAIL["id"]})),
        response(call("finish", {"headline": "Your lease renewal email", "summary": MAIL["body"],
                                 "blocks": [{"type": "emails", "message_ids": [MAIL["id"]]}]})),
    ])
    found = await _run(second, abilities, client, replay)
    # History remains context; it is not copied into the new run's tool state.
    assert [b["type"] for b in found.result["blocks"]] == ["emails"]
    assert "dentist" not in str(found.result).lower()
    assert client.calls[0]["input"][-1]["content"][0]["text"] == EMAIL
    assert any(t.get("name") == "list_espresso_events" for t in client.calls[0]["tools"])
    store.list_events.assert_not_awaited()
    store.create_event.assert_awaited_once()
    gmail.send_email.assert_not_awaited()


def test_scope_keeps_approved_action_outcome_instructions():
    text = prompt.build_system_prompt(context(resume=FrozenAction(tool="send_email", args={})), [])
    assert "The system then tried it itself" in text
    assert "Do not do it again" in text
    assert "if the outcome is an error or unknown, say so plainly" in text
