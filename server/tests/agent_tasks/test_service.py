"""Owner-scoped reads and writes, rounds settling, the waiting rule, tombstones."""
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work.agent_tasks import service
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import COMPANY, ITEM, NOW, TASK, USER, item_row, round_row, task_row


@pytest.fixture
def conn(monkeypatch):
    c = FakeConn()
    monkeypatch.setattr(service, "connection_or_direct", connection(c))
    return c


def test_views():
    view = service.task_view(task_row(seen_at=None))
    assert view["phase"] == "summarize" and view["unseen"] is True and view["brief"]["budget_max"] == 3500
    assert service.task_view(task_row(seen_at=NOW))["unseen"] is False
    assert service.phase_name({"phase": None}) is None
    assert service.round_view(round_row())["summary"] == {"headline": "Found 2"}
    plan = service.plan_view(task_row())
    assert [c["key"] for c in plan["columns"]] == ["price", "beds", "pets"]
    assert plan["constraints"][0]["label"] == "Price at most $3,500/mo"
    assert service.plan_view(task_row(plan="{}"))["columns"] == []
    assert service.plan_view(task_row(playbook="gone"))["constraints"] == []
    assert service.fingerprint(task_row()) == service.fingerprint(task_row())
    assert service.fingerprint(task_row(status="running")) != service.fingerprint(task_row())


@pytest.mark.asyncio
async def test_list_summary_and_get(conn):
    conn.on("FROM mw_agent_tasks t", [task_row()])
    conn.on("COUNT(*) FILTER", {"running": 1, "waiting": 2, "unseen": None})
    assert (await service.list_tasks(USER, COMPANY))[0]["id"] == str(TASK)
    assert conn.calls[-1][2] == (USER, COMPANY, ["chain", "job_search"])
    assert "t.engine = ANY($3::text[])" in conn.calls[-1][1]
    await service.list_tasks(USER, COMPANY, engines=("job_search",))
    assert conn.calls[-1][2][2] == ["job_search"]
    assert await service.summary(USER, COMPANY) == {"running": 1, "waiting": 2, "unseen": 0}
    assert "CASE WHEN t.engine = 'job_search'" in conn.calls[-1][1]

    conn.on("WHERE t.id = $1 AND t.user_id = $2", task_row())
    conn.on("FROM mw_agent_task_items WHERE task_id", [item_row()])
    conn.on("FROM mw_agent_task_rounds WHERE task_id", [round_row()])
    got = await service.get_task(TASK, USER)
    assert got["unseen"] is False
    assert got["items"][0]["fields"]["price"]["display"] == "$3,200/mo" and got["rounds"][0]["n"] == 1
    assert conn.ran("SET seen_at = NOW()")
    conn.calls.clear()
    await service.get_task(TASK, USER, mark_seen=False)
    assert not conn.ran("SET seen_at")

    conn.on("WHERE t.id = $1 AND t.user_id = $2", None)
    with pytest.raises(service.AgentTaskError) as exc:
        await service.get_task(TASK, USER)
    assert exc.value.code == 404


@pytest.mark.asyncio
async def test_status_nudges_a_live_chain(conn, monkeypatch):
    from app.matcha.services.matcha_work.agent_tasks import orchestrator

    nudge = AsyncMock(return_value=False)
    monkeypatch.setattr(orchestrator, "nudge", nudge)
    conn.on("WHERE t.id = $1 AND t.user_id = $2", task_row(status="running"))
    view = await service.status_view(TASK, USER)
    assert view["status"] == "running" and view["phase"] == "summarize"
    nudge.assert_awaited_once_with(TASK)
    conn.on("WHERE t.id = $1 AND t.user_id = $2", task_row())
    await service.status_view(TASK, USER)
    assert nudge.await_count == 1


@pytest.mark.asyncio
async def test_items_and_dismissing_reranks(conn, monkeypatch):
    conn.on("WHERE t.id = $1 AND t.user_id = $2", task_row())
    conn.on("FROM mw_agent_task_items WHERE id = $1 AND task_id = $2", item_row())
    assert (await service.get_item(TASK, ITEM, USER))["fields"]["price"]["evidence"]["origin"] == "page_text"
    # A product carries what it can do (Buy) and what was done with it.
    conn.on("FROM mw_agent_task_items WHERE id = $1 AND task_id = $2",
            item_row(kind="product", url="https://shop.test/products/balm"))
    conn.on("FROM mw_agent_task_actions", [{"id": ITEM, "item_id": ITEM, "action": "buy", "status": "done",
                                            "preview": "{}", "result": '{"url": "u"}', "error": None}])
    detail = await service.get_item(TASK, ITEM, USER, user=None)
    assert [a["key"] for a in detail["actions"]] == ["buy"] and detail["action_history"][0]["status"] == "done"
    conn.on("FROM mw_agent_task_items WHERE id = $1 AND task_id = $2", item_row())
    conn.on("deleted_at IS NULL FOR UPDATE", task_row())
    conn.on("UPDATE mw_agent_task_items SET user_state", item_row(user_state="dismissed"))
    called = AsyncMock()
    monkeypatch.setattr(service, "_rerank", called)
    await service.patch_item(TASK, ITEM, USER, user_state="dismissed", notes=None)
    assert conn.ran("SET user_state = $3")[0][2][2:] == ("dismissed", "") and called.await_count == 1
    await service.patch_item(TASK, ITEM, USER, user_state=None, notes="call them")
    assert called.await_count == 1
    conn.on("FROM mw_agent_task_items WHERE id = $1 AND task_id = $2", None)
    for call in (service.get_item(TASK, ITEM, USER),
                 service.patch_item(TASK, ITEM, USER, user_state="saved", notes=None)):
        with pytest.raises(service.AgentTaskError):
            await call


@pytest.mark.asyncio
async def test_rerank_goes_through_the_playbook(monkeypatch):
    rerank = AsyncMock()
    monkeypatch.setattr(service.playbooks, "get", lambda key: type("P", (), {"rerank": rerank})() if key else None)
    await service._rerank("conn", task_row())
    rerank.assert_awaited_once()
    await service._rerank("conn", task_row(playbook=None))
    assert rerank.await_count == 1


@pytest.mark.asyncio
async def test_close_round_rules():
    c = FakeConn()
    await service.close_round(c, TASK)
    settle, wait = c.calls
    assert "t.phase_cursor ? 'round_failed'" in settle[1] and "r.kind = 'more' AND NOT" in settle[1]
    assert "r.items_added = 0 OR" in settle[1]
    assert "t.status <> 'waiting'" in settle[1] and "waiting_since = COALESCE" in wait[1]


@pytest.mark.asyncio
async def test_cancel_and_delete(conn, monkeypatch):
    monkeypatch.setattr(service, "_rerank", AsyncMock())
    monkeypatch.setattr(service, "get_task", AsyncMock(return_value={"status": "cancelled"}))
    conn.on("WHERE t.id = $1 AND t.user_id = $2", task_row(status="running"))
    conn.on("deleted_at IS NULL FOR UPDATE", task_row(status="running"))
    conn.on("SET status = 'cancelled', dispatch_token = NULL", task_row(status="cancelled"))
    assert (await service.cancel_task(TASK, USER))["status"] == "cancelled"
    assert conn.ran("UPDATE mw_agent_task_rounds r") and service._rerank.await_count == 1
    conn.calls.clear()
    conn.on("deleted_at IS NULL FOR UPDATE", task_row(status="done"))
    await service.cancel_task(TASK, USER)
    assert not conn.ran("SET status = 'cancelled'")

    conn.calls.clear()
    assert await service.delete_task(TASK, USER) == {"deleted": True}
    assert conn.ran("DELETE FROM mw_agent_task_items") and conn.ran("DELETE FROM mw_project_agent_runs")
    assert conn.ran("SET directive = '', scope") and conn.ran("SET deleted_at = NOW()")


@pytest.mark.asyncio
async def test_end_stale_and_expire_waiting(conn, monkeypatch):
    monkeypatch.setattr(service, "_rerank", AsyncMock())
    c = FakeConn().on("FOR UPDATE", [task_row(id=TASK), task_row(id=ITEM)])
    c.on("SELECT EXISTS", lambda task_id: task_id == TASK)
    assert await service.end_stale(c, USER) == 2
    statuses = [call[2][1] for call in c.ran("SET status = $2")]
    assert statuses == ["done", "failed"] and service._rerank.await_count == 1

    conn.on("WHERE status = 'waiting'", [{"id": TASK, "current_round": 2}])
    assert await service.expire_waiting() == 1
    [settle] = conn.ran("SET status = 'failed'")
    assert settle[2] == ([TASK], [2])
    conn.on("WHERE status = 'waiting'", [])
    conn.calls.clear()
    assert await service.expire_waiting() == 0 and not conn.ran("SET status = 'failed'")


@pytest.mark.asyncio
async def test_find_by_request(conn):
    conn.on("request_id = $2", task_row())
    assert (await service.find_by_request(USER, TASK))["id"] == str(TASK)
    conn.on("request_id = $2", None)
    assert await service.find_by_request(USER, TASK) is None


@pytest.mark.asyncio
async def test_history_cursor_is_stable_scoped_and_has_no_boundary_overlap(conn):
    from uuid import UUID

    rows = [task_row(id=UUID(int=n + 1)) for n in range(51)]
    conn.on("FROM mw_agent_tasks t", rows)
    page = await service.list_task_page(USER, COMPANY, engines=("job_search",))
    assert len(page["tasks"]) == 50
    assert page["next_cursor"] == f"{rows[49]['created_at'].isoformat()}|{rows[49]['id']}"
    sql, args = conn.calls[-1][1:]
    assert "ORDER BY t.created_at DESC, t.id DESC LIMIT 51" in sql
    assert args == (USER, COMPANY, ["job_search"])
    conn.on("FROM mw_agent_tasks t", rows[50:])
    last = await service.list_task_page(USER, COMPANY, engines=("job_search",), cursor=page["next_cursor"])
    assert [t["id"] for t in last["tasks"]] == [str(rows[50]["id"])]
    assert last["next_cursor"] is None
    sql, args = conn.calls[-1][1:]
    assert "(t.created_at, t.id) < ($4, $5)" in sql
    assert "t.user_id = $1 AND t.company_id = $2 AND t.deleted_at IS NULL" in sql
    assert args == (USER, COMPANY, ["job_search"], rows[49]["created_at"], rows[49]["id"])
    conn.on("FROM mw_agent_tasks t", [])
    assert await service.list_task_page(USER, COMPANY) == {"tasks": [], "next_cursor": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", ["garbage", "2026-10-17|no-id", "2026-10-17T00:00:00|" + str(TASK),
                                    "2026-10-17T00:00:00+00:00|bad-id"])
async def test_history_rejects_invalid_cursors_before_reading(conn, cursor):
    with pytest.raises(service.AgentTaskError) as exc:
        await service.list_task_page(USER, COMPANY, cursor=cursor)
    assert exc.value.code == 400
    assert not conn.calls
