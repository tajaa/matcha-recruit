"""Emailing the person what a task found once it finishes."""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work.agent_tasks import (
    chat, items as items_mod, job_tasks, mail, notify, orchestrator, service,
)
from tests.agent_runtime.helpers import FakeConn
from tests.job_search._fixtures import lead_row

from ._fixtures import ITEM, NOW, TASK, USER, item_row, price, task_row

SUMMARY = {"headline": "Two fit, both take dogs", "summary": "The best is a block from BART.",
           "top": [{"item_id": str(ITEM), "why": "A block from 16th St BART"}]}
USER_ROW = {"email": "renter@example.com", "is_active": True, "is_suspended": False}


def _pick(**over):
    fields = {"price": price(3200), "beds": {"value": 1, "display": "1 bd", "status": "verified"},
              "pets": {"value": None, "display": "Dogs?", "status": "unknown"}}
    units = [{"id": "a", "rent": 3300.0, "net_rent": 2949.0}, {"id": "b", "rent": 3600.0}]
    return items_mod.item_summary(item_row(
        fields=json.dumps(fields), images=json.dumps([{"url": "https://cdn.test/a.webp"}]),
        units=json.dumps(units), rank_explain=json.dumps({"flags": [], "units_fit": ["a"]}), **over))


def _labels():
    return {c["key"]: c["label"] for c in service.plan_view(task_row())["columns"]}


def test_a_finished_tasks_email_has_its_headline_and_picks():
    columns = service.plan_view(task_row())["columns"]
    message = mail.compose(task_row(), summary=SUMMARY, top=[_pick()], columns=columns)
    labels = _labels()
    assert message["subject"] == "Done: 1bd in SF"
    for part in ("Two fit, both take dogs", "The best is a block from BART.", "A block from 16th St BART",
                 'href="https://apts.test/1"', 'src="https://cdn.test/a.webp"',
                 f"{labels['price']}: $3,200/mo", f"{labels['beds']}: 1 bd", "1 of 2 homes fit · from $2,949/mo"):
        assert part in message["html"], part
    assert "Dogs?" not in message["html"]  # unconfirmed facts aren't stated
    text = message["text"]
    assert text.startswith("Done: 1bd in SF\n\nTwo fit, both take dogs")
    assert "1. Sunny 1BR (Mission)" in text and "   https://apts.test/1" in text
    assert "Open Espresso and go to Tasks" in text


def test_an_email_never_carries_markup_or_a_link_that_isnt_a_web_page():
    pick = _pick(title="<script>x</script>", url="javascript:alert(1)")
    message = mail.compose(task_row(title="<b>1bd</b>"), summary={}, top=[pick], columns=[])
    assert "<script>" not in message["html"] and "&lt;script&gt;" in message["html"]
    assert "<b>1bd</b>" not in message["html"] and "javascript:" not in message["html"]
    assert "javascript:" not in message["text"]


def test_a_stopped_tasks_email_says_why():
    task = task_row(status="failed", error="It ran out of time.", progress='{"note": "Searching"}')
    message = mail.compose(task, summary=SUMMARY, top=[], columns=[])
    assert message["subject"] == "Stopped: 1bd in SF"
    assert "It ran out of time." in message["text"] and "Two fit" not in message["text"]
    # No headline or summary: the note it stopped on.
    done = mail.compose(task_row(progress='{"note": "Stopped early: out of searches"}'), summary={}, top=[],
                        columns=[])
    assert "Stopped early: out of searches" in done["text"]


def test_homes_and_facts_read_as_the_app_says_them():
    assert mail.homes_line(None) is None and mail.homes_line({"count": 0}) is None
    assert mail.homes_line({"count": 1, "fit": None, "from": None}) == "1 home listed"
    assert mail.homes_line({"count": 18, "fit": 0, "from": 2949.0}) == "None of 18 homes fit"
    assert mail.homes_line({"count": 2, "fit": None, "from": 2949.0}) == "2 homes listed · from $2,949/mo"
    assert mail.homes_line({"count": 18, "fit": 3, "from": 2949.0}) == "3 of 18 homes fit · from $2,949/mo"
    item = {"subtitle": "Acme", "fields": {
        "company": {"display": "Acme", "status": "verified"},  # the subtitle again
        "pay": {"display": "$200k", "status": "verified"},
        **{f"f{n}": {"display": str(n), "status": "verified"} for n in range(6)}}}
    shown = mail.facts(item, [{"key": "f5", "label": "Five"}])
    assert shown[0] == ("Five", "5") and ("Pay", "$200k") in shown and len(shown) == mail.FACTS


def _finished(**over):
    return {"id": TASK, "user_id": USER, "playbook": "research", "title": "1bd in SF", "directive": "x",
            "status": "done", "progress": '{"note": "Found 2"}', "error": None, "plan": task_row()["plan"],
            "summary": json.dumps(SUMMARY), "asked_at": NOW - timedelta(minutes=6), "settled_at": NOW, **over}


def _conn(task, user=USER_ROW):
    return (FakeConn().on("JOIN mw_agent_task_rounds r", task).on("FROM users WHERE id", user)
            .on("FROM mw_agent_task_items WHERE task_id = $1 AND rank_band < 9", [item_row()]))


@pytest.mark.asyncio
async def test_a_finished_round_is_emailed_to_the_accounts_address(monkeypatch):
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(mail, "_send", send)
    assert await mail.round_finished(_conn(_finished()), TASK) is True
    to, message, _ = send.await_args.args
    assert to == "renter@example.com" and message["subject"] == "Done: 1bd in SF"
    assert "Sunny 1BR" in message["text"]
    # A quick round (a refine that only re-sorts): the person is there.
    send.reset_mock()
    quick = _finished(asked_at=NOW - timedelta(seconds=20))
    assert await mail.round_finished(_conn(quick), TASK) is False
    # Waiting or cancelled, no such task, no address, a closed account: nothing.
    for conn in (_conn(_finished(status="waiting")), _conn(_finished(status="cancelled")), _conn(None),
                 _conn(_finished(), None), _conn(_finished(), {**USER_ROW, "email": None}),
                 _conn(_finished(), {**USER_ROW, "is_active": False}),
                 _conn(_finished(), {**USER_ROW, "is_suspended": True})):
        assert await mail.round_finished(conn, TASK) is False
    send.assert_not_awaited()
    # A failure never fails the task.
    broken = FakeConn().on("JOIN mw_agent_task_rounds r", RuntimeError("db"))
    assert await mail.round_finished(broken, TASK) is False


@pytest.mark.asyncio
async def test_the_email_goes_out_as_espresso(monkeypatch):
    from app.core.services import email as email_pkg

    service_ = SimpleNamespace(is_configured=lambda: True, send_email_with_fallback=AsyncMock(return_value=True))
    monkeypatch.setattr(email_pkg, "get_email_service", lambda: service_)
    message = {"subject": "Done: x", "html": "<p>x</p>", "text": "x"}
    assert await mail._send("renter@example.com", message, TASK) is True
    kwargs = service_.send_email_with_fallback.await_args.kwargs
    assert kwargs["from_name"] == "Espresso" and kwargs["to_email"] == "renter@example.com"
    assert kwargs["text_content"] == "x"
    service_.is_configured = lambda: False
    service_.send_email_with_fallback.reset_mock()
    assert await mail._send("renter@example.com", message, TASK) is False
    service_.send_email_with_fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_round_is_settled_and_emailed_once():
    conn = FakeConn().on("UPDATE mw_agent_task_rounds r", "UPDATE 1")
    assert await service.close_round(conn, TASK) is True
    conn = FakeConn().on("UPDATE mw_agent_task_rounds r", "UPDATE 0")
    assert await service.close_round(conn, TASK) is False


@pytest.mark.asyncio
async def test_a_stopped_task_emails_only_the_round_it_settled(monkeypatch):
    monkeypatch.setattr(orchestrator.notify, "task_stopped", AsyncMock())
    monkeypatch.setattr(orchestrator.chat, "post_stopped", AsyncMock(return_value=None))
    emailed = AsyncMock()
    monkeypatch.setattr(orchestrator.mail, "round_finished", emailed)
    monkeypatch.setattr(orchestrator.service, "close_round", AsyncMock(return_value=True))
    await orchestrator._stopped("conn", TASK)
    emailed.assert_awaited_once_with("conn", TASK)
    emailed.reset_mock()
    monkeypatch.setattr(orchestrator.service, "close_round", AsyncMock(return_value=False))
    await orchestrator._stopped("conn", TASK)  # settled already, or waiting on the person
    emailed.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_finished_job_search_is_emailed_its_top_jobs(monkeypatch):
    from tests.agent_tasks.test_job_tasks import SEARCH, pointer

    monkeypatch.setattr(notify, "tell", AsyncMock())
    monkeypatch.setattr(chat, "post_card", AsyncMock(return_value=None))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(mail, "_send", send)
    conn = (FakeConn().on("WHERE t.job_search_id = $1", pointer(js_status="done", js_completed_at=NOW))
            .on("FROM mw_job_leads WHERE search_id = $1", [lead_row()]).on("FROM users WHERE id", USER_ROW))
    await job_tasks.search_stopped(conn, SEARCH)
    to, message, _ = send.await_args.args
    assert to == "renter@example.com" and message["subject"] == "Done: COO"
    assert "1. COO" in message["text"]
    # Cancelled, or no address: no email; a failure never raises.
    send.reset_mock()
    assert await mail.search_finished(FakeConn(), {"id": TASK, "user_id": USER, "status": "cancelled"}, []) is False
    assert await mail.search_finished(FakeConn(), {"id": TASK, "user_id": USER, "status": "done"}, []) is False
    broken = FakeConn().on("FROM users WHERE id", RuntimeError("db"))
    assert await mail.search_finished(broken, {"id": TASK, "user_id": USER, "status": "failed"}, []) is False
    send.assert_not_awaited()
