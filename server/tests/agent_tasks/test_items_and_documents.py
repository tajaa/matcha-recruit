"""Storing findings, writing them up, and telling the person."""
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work import journal_service
from app.matcha.services.matcha_work.agent_tasks import document, items, model_run, notify
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import COMPANY, ITEM, TASK, TODAY, TOKEN, USER, item_row, price, task_row


def test_dedupe_keys():
    assert items.dedupe_key({"url": "https://www.apts.test/1/?utm_source=x"}) == "u:https://apts.test/1"
    assert items.dedupe_key({"title": "Sunny  1BR!", "subtitle": "Mission"}) == "t:sunny 1br|mission"
    assert items.title_key(None) == ""


@pytest.mark.asyncio
async def test_insert_skips_repeats_and_counts_the_round():
    conn = FakeConn().on("SELECT dedupe_key, title", [{"dedupe_key": "u:https://apts.test/1", "title": "Old one"}])
    conn.on("WITH ins AS", 2)
    records = [
        {"url": "https://apts.test/1", "title": "Again"},                      # same page
        {"url": "https://apts.test/2", "title": "Old one"},                    # same name
        {"url": "https://apts.test/2", "title": "Old one", "origin": "provider"},  # a provider's is kept
        {"url": "https://apts.test/3", "title": "New"},
        {"url": "https://apts.test/3", "title": "New"},                        # repeat in the batch
        {"url": "https://apts.test/4", "title": "Over the room"},
    ]
    assert await items.insert_items(conn, task_row(), TOKEN, 2, records, room=2) == 2
    rows = json.loads(conn.ran("WITH ins AS")[0][2][2])
    assert [r["url"] for r in rows] == ["https://apts.test/2", "https://apts.test/3"]
    assert conn.ran("SET items_added = items_added + $3")[0][2] == (TASK, 2, 2)
    assert await items.insert_items(conn, task_row(), TOKEN, 1, records, room=0) == 0
    empty = FakeConn().on("SELECT dedupe_key, title", [{"dedupe_key": "u:https://apts.test/1", "title": "x"}])
    assert await items.insert_items(empty, task_row(), TOKEN, 1, records[:1], room=5) == 0
    none_added = FakeConn().on("WITH ins AS", 0)
    assert await items.insert_items(none_added, task_row(), TOKEN, 1, records[3:4], room=5) == 0
    assert not none_added.ran("items_added")


def test_item_views():
    summary = items.item_summary(item_row(fields=json.dumps({"price": price(3200), "x": "junk"})))
    assert summary["fields"] == {"price": {"display": "$3,200/mo", "value": 3200, "status": "verified",
                                           "unit": "month", "currency": "USD"}}
    detail = items.item_detail(item_row())
    assert detail["fields"]["price"]["evidence"]["origin"] == "page_text" and detail["fit_reasons"] == ["Close to transit"]
    assert items.as_rank_input(item_row())["fields"]["price"]["value"] == 3200
    assert items.view_for_model(item_row())["rank_explain"] == {"flags": []}


def test_render_is_plain_safe_markdown():
    rows = [
        item_row(title="Sunny [1BR](javascript:x) | <b>", notes="Call Tue", fields=json.dumps({
            "price": price(3200), "pets": {"value": ["dogs"], "display": "Dogs OK", "status": "claimed",
                                            "evidence": {"quote": "dogs ok", "url": "https://blog.test/(x)", "origin": "model"}},
            "zzz": {"display": "x"}})),
        item_row(id=uuid4(), title="No link", url=None, subtitle="", fit_reasons="[]", fields="{}"),
    ]
    title, md = document.render(task_row(), rows, today=TODAY)
    assert title == "1bd in SF — findings" and "As of October 14, 2026. 2 shown." in md
    assert "## What it looked for" in md and "- Where: San Francisco" in md and "Price at most $3,500/mo" in md
    assert "| # | Name | Price | Beds | Pets |" in md
    assert "Sunny \\[1BR\\](javascript:x) \\| \\<b\\>" in md and "javascript:x)" not in md.replace("\\[1BR\\](javascript:x)", "")
    assert "Dogs OK (unconfirmed)" in md and "(https://blog.test/%28x%29)" in md
    assert "- Your notes: Call Tue" in md and "## Sources" in md and "| 2 | No link | — | — | — |" in md
    bare, md = document.render(task_row(playbook="gone", plan="{}", title=""), [], today=TODAY)
    assert bare.startswith("find me") and "## Top picks" not in md


@pytest.mark.asyncio
async def test_pick_rows_and_write(monkeypatch):
    conn = FakeConn().on("FROM mw_agent_task_items", [item_row()])
    assert len(await document.pick_rows(conn, TASK, [ITEM])) == 1
    assert "id = ANY($2::uuid[])" in conn.calls[-1][1]
    await document.pick_rows(conn, TASK, [])
    assert "user_state IN ('saved', 'chosen')" in conn.calls[-1][1]
    note = AsyncMock(return_value={"id": "j1", "entry_id": "e1"})
    monkeypatch.setattr(journal_service, "create_note_direct", note)
    made = await document.write(conn, task_row(), item_ids=[], today=TODAY)
    assert made == {"journal_id": "j1", "entry_id": "e1", "title": "1bd in SF — findings", "items": 1}
    assert note.await_args.args[1:] == (USER, COMPANY)


@pytest.mark.asyncio
async def test_create_note_direct_binds_the_user_for_rls():
    conn = FakeConn().on("FROM mw_journal_folders", uuid4())
    conn.on("INSERT INTO mw_journals", {"id": uuid4(), "title": "T", "description": None, "color": None,
                                        "icon": "note.text", "status": "active", "kind": "note", "folder_id": None,
                                        "created_by": USER, "created_at": None, "updated_at": None})
    conn.on("INSERT INTO mw_journal_entries", "entry-1")
    note = await journal_service.create_note_direct(conn, USER, COMPANY, title="T", content="# hi")
    assert note["entry_id"] == "entry-1" and note["kind"] == "note"
    assert conn.calls[0][1].startswith("SELECT set_config('app.current_user_id', $1, true)")
    assert conn.calls[0][2] == (str(USER),)


def test_notification_wording():
    assert notify.link_for(TASK) == f"/espresso/tasks/{TASK}"
    assert notify.message_for(task_row()) == ("agent_task_done", "Done: 1bd in SF", "Found 3")
    assert notify.message_for(task_row(status="failed", error="Nothing matched"))[1:] == ("Stopped: 1bd in SF", "Nothing matched")
    waiting = notify.message_for(task_row(status="waiting", needs=json.dumps({"prompt": "Which date?"})))
    assert waiting == ("agent_task_needs_you", "Needs you: 1bd in SF", "Which date?")
    assert notify.message_for(task_row(status="cancelled")) is None


@pytest.mark.asyncio
async def test_task_stopped_notifies_on_the_callers_connection(monkeypatch):
    from app.matcha.services import notification_service

    create = AsyncMock()
    monkeypatch.setattr(notification_service, "create_notification", create)
    conn = FakeConn().on("FROM mw_agent_tasks WHERE id = $1", task_row())
    await notify.task_stopped(conn, TASK)
    kwargs = create.await_args.kwargs
    assert kwargs["conn"] is conn and kwargs["type"] == "agent_task_done" and kwargs["metadata"]["task_id"] == str(TASK)
    conn.on("FROM mw_agent_tasks WHERE id = $1", task_row(status="cancelled"))
    await notify.task_stopped(conn, TASK)
    conn.on("FROM mw_agent_tasks WHERE id = $1", None)
    await notify.task_stopped(conn, TASK)
    assert create.await_count == 1
    create.side_effect = RuntimeError("bell down")
    conn.on("FROM mw_agent_tasks WHERE id = $1", task_row())
    await notify.task_stopped(conn, TASK)  # never raises


@pytest.mark.asyncio
async def test_create_notification_can_use_the_callers_connection(monkeypatch):
    from app.matcha.services import notification_service

    row = {"id": uuid4(), "user_id": USER, "company_id": COMPANY, "type": "agent_task_done", "title": "Done",
           "body": None, "link": None, "metadata": "{}", "is_read": False, "created_at": None}
    conn = FakeConn().on("INSERT INTO mw_notifications", row)

    def no_pool():
        raise AssertionError("the pool must not be used")

    monkeypatch.setattr(notification_service, "get_connection", no_pool)
    out = await notification_service.create_notification(user_id=USER, company_id=COMPANY, type="agent_task_done",
                                                         title="Done", conn=conn)
    assert out["id"] == row["id"] and "agent_task_done" in notification_service.TYPES


@pytest.mark.asyncio
async def test_a_tasks_model_runs_are_its_own(monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime import models, phase_run

    monkeypatch.setattr(models, "offered", lambda: {"luna", "claude-x"})
    owner = model_run.run_owner(task_row(model="claude-x"))
    assert (owner.kind, owner.fk_column, owner.surface) == ("agent_task", "agent_task_id", "agent_task")
    assert owner.usage_feature == "matcha.espresso.tasks.research" and owner.model == "claude-x"
    assert model_run.model_for({"model": "gone"}) == model_run.LUNA
    conn = FakeConn()
    monkeypatch.setattr(model_run, "connection_or_direct", connection(conn))
    await owner.account({"token_usage": {"total_tokens": 40}})
    assert conn.ran("model_runs = model_runs + 1")[0][2] == (TASK, 40)
    run = AsyncMock(return_value="outcome")
    monkeypatch.setattr(phase_run, "run_model_phase", run)
    assert await model_run.run_model_phase(task_row(), phase="plan") == "outcome"
    assert run.await_args.kwargs == {"phase": "plan"}
    from app.core.services import anthropic_messages

    monkeypatch.setattr(anthropic_messages, "claude_override", AsyncMock(return_value=None))
    assert await model_run.default_model() == model_run.LUNA
