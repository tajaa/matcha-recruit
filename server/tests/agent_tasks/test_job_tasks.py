"""Job searches as Tasks: pointer rows, their state read from the search, starting one, telling."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.matcha_work.agent_tasks import AgentTaskCreate, RoundCreate
from app.matcha.services.matcha_work.agent_tasks import enqueue, job_tasks, notify, playbooks, service
from app.matcha.services.matcha_work.job_search import orchestrator as job_orchestrator
from app.matcha.services.matcha_work.job_search import service as job_service
from tests.agent_runtime.helpers import FakeConn, connection
from tests.job_search._fixtures import lead_row, search_row

from ._fixtures import COMPANY, NOW, TASK, USER, task_row

SEARCH = uuid4()


def pointer(**over):
    """A pointer row as the service reads it: the task's columns, then its search's (`js_*`)."""
    own = dict(playbook="job_search", engine="job_search", job_search_id=SEARCH, request_id=SEARCH,
               status="done", title="", directive="", phase=None, plan="{}", brief="{}", completed_at=None,
               item_count=0, shown_count=0)
    search = {"js_status": "discovering", "js_title": "COO", "js_ask": "COO roles across the US",
              "js_progress": '{"note": "Searching"}', "js_error": None, "js_updated_at": NOW,
              "js_started_at": NOW, "js_completed_at": None, "js_deleted_at": None, "js_lead_count": 12,
              "js_shown_count": 9}
    for key, value in over.items():
        (search if key.startswith("js_") else own)[key] = value
    return task_row(**own, **search)


@pytest.fixture
def conn(monkeypatch):
    c = FakeConn()
    monkeypatch.setattr(service, "connection_or_direct", connection(c))
    return c


# ── reading a pointer ─────────────────────────────────────────────────────────

def test_a_pointer_shows_its_searchs_state():
    view = service.task_view(pointer())
    assert view["status"] == "running" and view["phase"] == "discovering" and view["engine"] == "job_search"
    assert view["title"] == "COO" and view["directive"] == "COO roles across the US"
    assert view["progress"] == {"note": "Searching"} and view["item_count"] == 12 and view["shown_count"] == 9
    assert view["job_search_id"] == str(SEARCH) and view["unseen"] is False
    for search_status, shown in (("queued", "queued"), ("approaching", "running"), ("done", "done"),
                                 ("failed", "failed"), ("cancelled", "cancelled")):
        assert service.task_view(pointer(js_status=search_status))["status"] == shown
    done = service.task_view(pointer(js_status="done", js_completed_at=NOW))
    assert done["completed_at"] == NOW.isoformat() and done["unseen"] is True
    # A chain task and a pointer whose search wasn't joined are left alone.
    assert job_tasks.overlay({"engine": "chain", "status": "done"}) == {"engine": "chain", "status": "done"}
    assert job_tasks.overlay({"engine": "job_search", "status": "done"})["status"] == "done"
    assert service.task_view(task_row())["job_search_id"] is None
    # The fingerprint moves with the search, not the pointer.
    assert service.fingerprint(pointer()) != service.fingerprint(pointer(js_status="done"))
    assert "WHEN 'cancelled' THEN 'cancelled'" in job_tasks.STATUS_SQL and "ELSE 'running'" in job_tasks.STATUS_SQL


def test_a_job_reads_as_a_finding():
    lead = job_service.lead_summary(lead_row(remote=True, screen_status="relevant"))
    item = job_tasks.lead_item(lead)
    assert item["title"] == "COO" and item["subtitle"] == "Acme" and item["status"] == "verified"
    assert item["fields"]["pay"]["status"] == "verified" and item["fields"]["pay"]["currency"] == "USD"
    assert item["fields"]["location"]["display"] == "Austin, TX · Remote"
    assert item["url"] == "https://boards.greenhouse.io/acme/jobs/1"
    unposted = job_tasks.lead_item(job_service.lead_summary(lead_row(
        comp="{}", comp_status="not_disclosed", comp_annual_min=None, comp_currency=None,
        screen_status="irrelevant", location="", remote=True, apply_links="[]",
    )))
    # Pay a posting doesn't state is unknown, never zero.
    assert unposted["fields"]["pay"]["status"] == "unknown" and "currency" not in unposted["fields"]["pay"]
    assert unposted["status"] == "irrelevant" and unposted["fields"]["location"]["display"] == "Remote"
    assert unposted["url"] == "https://boards.greenhouse.io/acme/jobs/1"  # the posting, without an apply link
    assert job_tasks.lead_item({"id": "x"})["fields"]["pay"]["display"] == "Not posted"


# ── the playbook ──────────────────────────────────────────────────────────────

def test_the_job_search_playbook():
    book = playbooks.get("job_search")
    assert book is job_tasks.PLAYBOOK and book.engine == "job_search" and book.consent == "jobs"
    book.validate()
    assert "job_search" in playbooks.startable_keys() and "research" in playbooks.startable_keys()
    # No listings key needed: a search finds its postings on the web.
    assert playbooks.startable(book) and not playbooks.startable(None)
    assert book.view()["intake"][2]["options"] == ["Any", "Remote only", "On-site only"]


def test_a_job_search_brief_is_checked():
    brief = job_tasks.validate_brief({"titles": ["COO", "coo", "VP Ops"], "locations": ["Austin"],
                                      "remote": "Remote only", "base_floor": 250000.0, "use_resume": True})
    assert brief == {"titles": ["COO", "VP Ops"], "locations": ["Austin"], "remote": "remote_only",
                     "base_floor": 250000, "use_resume": True}
    loose = job_tasks.validate_brief({"remote": "onsite_only", "use_resume": "yes"})
    assert loose["remote"] == "onsite_only" and loose["use_resume"] is False and loose["base_floor"] is None
    assert job_tasks.validate_brief({"remote": "somewhere"})["remote"] == "any"
    with pytest.raises(ValueError):
        job_tasks.validate_brief({"titles": [f"t{i}" for i in range(9)]})


# ── creating and starting ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_pointer_is_written_with_the_search():
    c = FakeConn()
    channel, message = uuid4(), uuid4()
    await job_tasks.insert_pointer(c, search_row(id=SEARCH), origin=(channel, message))
    [insert] = c.ran("INSERT INTO mw_agent_tasks")
    assert "ON CONFLICT DO NOTHING" in insert[1] and "'done'" in insert[1]
    assert insert[2][0] == SEARCH and insert[2][3:5] == ("job_search", "job_search")
    assert insert[2][5:9] == ("COO", "COO roles across the US", channel, message)
    await job_tasks.insert_pointer(c, search_row(id=SEARCH, title=None, ask=None))
    assert c.ran("INSERT INTO mw_agent_tasks")[1][2][5:9] == ("", "", None, None)


@pytest.mark.asyncio
async def test_starting_a_job_search_task(monkeypatch):
    from app.matcha.services.matcha_work.job_search import enqueue as job_enqueue

    from app.matcha.services.matcha_work.job_search import service as search_service

    created = AsyncMock(return_value={"id": str(SEARCH)})
    monkeypatch.setattr(job_enqueue, "create_search", created)
    monkeypatch.setattr(service, "task_for_search", AsyncMock(return_value={"id": "task"}))
    monkeypatch.setattr(search_service, "resume_on_file", AsyncMock(return_value={"filename": "cv.pdf"}))
    user = SimpleNamespace(id=USER, role="individual")
    body = AgentTaskCreate(request_id=uuid4(), playbook="job_search", directive="COO roles, pay matters most",
                           title="COO roles", consent_version="jobs-1")
    brief = job_tasks.validate_brief({"titles": ["COO"], "remote": "Any", "base_floor": 200000,
                                      "use_resume": True})
    origin = (uuid4(), uuid4())
    assert await job_tasks.start(user, COMPANY, body, brief, origin=origin) == {"id": "task"}
    (got_user, got_company, create), kwargs = created.await_args.args, created.await_args.kwargs
    assert got_user is user and got_company == COMPANY and kwargs == {"origin": origin}
    assert create.request_id == body.request_id and create.ask == body.directive and create.title == "COO roles"
    assert create.criteria.titles == ["COO"] and create.criteria.base_floor == 200000
    assert create.use_resume is True and create.consent_version == "jobs-1"
    assert service.task_for_search.await_args.args == (USER, SEARCH)


@pytest.mark.asyncio
async def test_a_resume_search_needs_a_saved_resume(monkeypatch):
    from app.matcha.services.matcha_work.job_search import enqueue as job_enqueue
    from app.matcha.services.matcha_work.job_search import service as search_service

    created = AsyncMock()
    monkeypatch.setattr(job_enqueue, "create_search", created)
    monkeypatch.setattr(search_service, "resume_on_file", AsyncMock(return_value=None))
    body = AgentTaskCreate(request_id=uuid4(), playbook="job_search", directive="COO roles")
    user = SimpleNamespace(id=USER, role="individual")
    with pytest.raises(HTTPException) as exc:
        await job_tasks.start(user, COMPANY, body, job_tasks.validate_brief({"titles": ["COO"], "use_resume": True}))
    assert exc.value.status_code == 422 and exc.value.detail["code"] == "form_invalid"
    assert exc.value.detail["errors"] == {"use_resume": job_tasks.RESUME_MISSING}
    assert not created.await_count
    # Without the résumé, nothing is checked: a general search starts.
    created.return_value = {"id": str(SEARCH)}
    monkeypatch.setattr(service, "task_for_search", AsyncMock(return_value={"id": "task"}))
    await job_tasks.start(user, COMPANY, body, job_tasks.validate_brief({"titles": ["COO"]}))
    assert created.await_count == 1


@pytest.mark.asyncio
async def test_create_task_sends_a_job_search_to_its_engine(monkeypatch):
    monkeypatch.setattr(service, "find_by_request", AsyncMock(return_value=None))
    started = AsyncMock(return_value={"id": "task"})
    monkeypatch.setattr(job_tasks, "start", started)
    body = AgentTaskCreate(request_id=uuid4(), playbook="job_search", directive="find me COO roles",
                           brief={"remote": "Any"})
    monkeypatch.setattr(enqueue, "tasks_enabled", lambda user: False)
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(SimpleNamespace(id=USER, role="individual"), COMPANY, body)
    assert exc.value.status_code == 403 and not started.await_count
    monkeypatch.setattr(enqueue, "tasks_enabled", lambda user: True)
    origin = (uuid4(), None)
    assert await enqueue.create_task(SimpleNamespace(id=USER, role="individual"), COMPANY, body,
                                     origin=origin) == {"id": "task"}
    assert started.await_args.args[3] == job_tasks.validate_brief({"remote": "Any"})
    assert started.await_args.kwargs == {"origin": origin}
    bad = AgentTaskCreate(request_id=uuid4(), playbook="job_search", directive="find me COO roles",
                          brief={"titles": [f"t{i}" for i in range(9)]})
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(SimpleNamespace(id=USER, role="individual"), COMPANY, bad)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_a_job_search_takes_no_rounds(monkeypatch):
    c = FakeConn().on("FOR UPDATE", pointer())
    monkeypatch.setattr(enqueue, "connection_or_direct", connection(c))
    monkeypatch.setattr(enqueue, "tasks_enabled", lambda user: True)
    admin = SimpleNamespace(id=USER, role="admin")
    with pytest.raises(HTTPException) as exc:
        await enqueue.start_round(admin, TASK, RoundCreate(request_id=uuid4(), kind="more"))
    assert exc.value.status_code == 409 and "What matters" in exc.value.detail
    assert not c.ran("INSERT INTO mw_agent_task_rounds")


# ── the service's job branches ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reading_a_job_search_task(conn, monkeypatch):
    leads = [job_service.lead_summary(lead_row())]
    monkeypatch.setattr(job_service, "get_search", AsyncMock(return_value={
        "id": str(SEARCH), "status": "done", "fingerprint": "fp", "leads": leads,
    }))
    conn.on("WHERE t.id = $1 AND t.user_id = $2", pointer(js_status="done", js_completed_at=NOW))
    got = await service.get_task(TASK, USER)
    assert got["status"] == "done" and got["fingerprint"] == "fp" and got["rounds"] == []
    assert got["items"][0]["title"] == "COO" and got["job_search"] == {"id": str(SEARCH), "status": "done",
                                                                        "fingerprint": "fp"}
    assert got["plan"]["columns"] == [] and got["unseen"] is False
    assert conn.ran("SET seen_at = NOW()")
    conn.calls.clear()
    conn.on("WHERE t.id = $1 AND t.user_id = $2", pointer())  # still running: nothing to mark seen
    await service.get_task(TASK, USER)
    assert not conn.ran("SET seen_at")

    missing = job_service.JobSearchError("Job search not found.", 404)
    monkeypatch.setattr(job_service, "get_search", AsyncMock(side_effect=missing))
    with pytest.raises(service.AgentTaskError) as exc:
        await service.get_task(TASK, USER)
    assert exc.value.code == 404


@pytest.mark.asyncio
async def test_a_job_search_tasks_status_cancel_and_delete(conn, monkeypatch):
    conn.on("WHERE t.id = $1 AND t.user_id = $2", pointer())
    monkeypatch.setattr(job_service, "status_view", AsyncMock(return_value={
        "id": str(SEARCH), "status": "enriching", "progress": {"note": "Reading"}, "error": None,
        "lead_count": 7, "updated_at": NOW.isoformat(), "fingerprint": "fp2",
    }))
    status = await service.status_view(TASK, USER)
    assert status == {"id": str(TASK), "status": "running", "phase": "enriching", "progress": {"note": "Reading"},
                      "error": None, "item_count": 7, "current_round": 0, "updated_at": NOW.isoformat(),
                      "fingerprint": "fp2"}
    assert job_service.status_view.await_args.args == (SEARCH, USER)

    monkeypatch.setattr(job_service, "cancel_search", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "get_task", AsyncMock(return_value={"status": "cancelled"}))
    assert (await service.cancel_task(TASK, USER))["status"] == "cancelled"
    assert job_service.cancel_search.await_args.args == (SEARCH, USER)
    assert not conn.ran("SET status = 'cancelled'")

    monkeypatch.setattr(job_service, "delete_search", AsyncMock(return_value={"deleted": True}))
    assert await service.delete_task(TASK, USER) == {"deleted": True}
    assert job_service.delete_search.await_args.args == (SEARCH, USER)
    assert not conn.ran("DELETE FROM mw_agent_task_items")

    conn.on("FOR UPDATE", pointer())
    for call in (service.get_item(TASK, uuid4(), USER),
                 service.patch_item(TASK, uuid4(), USER, user_state="saved", notes=None)):
        with pytest.raises(service.AgentTaskError) as exc:
            await call
        assert exc.value.code == 409


@pytest.mark.asyncio
async def test_a_search_without_its_row_gets_one(conn, monkeypatch):
    rows = iter([None, pointer()])  # not there, then there
    conn.on("t.job_search_id = $2", lambda *_a: next(rows))
    conn.on("FROM mw_job_searches WHERE id = $1", search_row(id=SEARCH))
    inserted = AsyncMock()
    monkeypatch.setattr(job_tasks, "insert_pointer", inserted)
    view = await service.task_for_search(USER, SEARCH)
    assert view["job_search_id"] == str(SEARCH) and inserted.await_count == 1

    conn.on("t.job_search_id = $2", None)
    conn.on("FROM mw_job_searches WHERE id = $1", None)
    with pytest.raises(service.AgentTaskError) as exc:
        await service.task_for_search(USER, SEARCH)
    assert exc.value.code == 404

    conn.on("t.job_search_id = $2", pointer())
    inserted.reset_mock()
    assert (await service.task_for_search(USER, SEARCH))["title"] == "COO" and not inserted.await_count


@pytest.mark.asyncio
async def test_old_search_lookup_is_independent_of_the_recent_list(conn, monkeypatch):
    # A search can fall out of list_tasks' newest 50 rows, but its unique
    # pointer is still resolved directly. No list scan or pointer repair.
    monkeypatch.setattr(service, "list_tasks", AsyncMock(return_value=[task_row() for _ in range(50)]))
    conn.on("t.job_search_id = $3", pointer())
    view = await service.find_search_task(USER, COMPANY, SEARCH)
    assert view["id"] == str(TASK) and view["job_search_id"] == str(SEARCH)
    service.list_tasks.assert_not_awaited()
    method, query, args = conn.calls[-1]
    assert method == "fetchrow" and "LIMIT" not in query
    assert args == (USER, COMPANY, SEARCH)
    assert "t.user_id = $1 AND t.company_id = $2 AND t.job_search_id = $3" in query
    assert "t.engine = 'job_search' AND t.deleted_at IS NULL" in query
    assert "s.id IS NOT NULL AND s.deleted_at IS NULL" in query
    assert not any(method == "execute" for method, _query, _args in conn.calls)


@pytest.mark.asyncio
async def test_search_lookup_never_recreates_missing_deleted_or_foreign_pointers(conn, monkeypatch):
    inserted = AsyncMock()
    monkeypatch.setattr(job_tasks, "insert_pointer", inserted)
    conn.on("t.job_search_id = $3", lambda uid, cid, sid: (
        pointer() if (uid, cid, sid) == (USER, COMPANY, SEARCH) else None
    ))
    for user, company, search in ((uuid4(), COMPANY, SEARCH), (USER, uuid4(), SEARCH), (USER, COMPANY, uuid4())):
        with pytest.raises(service.AgentTaskError) as exc:
            await service.find_search_task(user, company, search)
        assert exc.value.code == 404
    conn.on("t.job_search_id = $3", None)  # deleted or missing pointer/search
    with pytest.raises(service.AgentTaskError) as exc:
        await service.find_search_task(USER, COMPANY, SEARCH)
    assert exc.value.code == 404
    inserted.assert_not_awaited()


# ── when a search stops ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_finished_search_is_told_once_with_its_card(monkeypatch):
    from app.matcha.services.matcha_work.agent_tasks import chat
    from app.matcha.services.matcha_work.project_agent import chat as project_chat

    channel = uuid4()
    told = AsyncMock()
    monkeypatch.setattr(notify, "tell", told)
    posted = AsyncMock(return_value={"id": "message"})
    monkeypatch.setattr(chat, "post_card", posted)
    broadcast = AsyncMock()
    monkeypatch.setattr(project_chat, "broadcast_espresso_message", broadcast)
    c = FakeConn().on("WHERE t.job_search_id = $1", pointer(js_status="done", js_completed_at=NOW,
                                                            origin_channel_id=channel))
    c.on("FROM mw_job_leads l WHERE search_id = $1", [lead_row()])
    await job_tasks.search_stopped(c, SEARCH)
    assert c.ran("SET completed_at = NOW()")[0][2] == (TASK,)
    # The card's top jobs are the matches: none from below the fit floor.
    assert "l.rank_band < 8" in c.ran("FROM mw_job_leads l WHERE search_id = $1")[0][1]
    assert told.await_args.args[1]["status"] == "done" and told.await_args.args[1]["title"] == "COO"
    task, kwargs = posted.await_args.args[1], posted.await_args.kwargs
    assert task["progress"] == {"note": "Searching"} and kwargs["channel_id"] == channel
    assert kwargs["top"][0]["title"] == "COO"
    broadcast.assert_awaited_once_with({"id": "message"})

    # Told already (a redraft that ended later), or cancelled by them: nothing.
    for row in (pointer(js_status="done", completed_at=NOW), pointer(js_status="cancelled")):
        told.reset_mock()
        await job_tasks.search_stopped(FakeConn().on("WHERE t.job_search_id = $1", row), SEARCH)
        assert not told.await_count
    # A failed search started outside chat: told, no card.
    posted.reset_mock()
    await job_tasks.search_stopped(FakeConn().on("WHERE t.job_search_id = $1", pointer(js_status="failed")),
                                   SEARCH)
    assert told.await_count == 1 and not posted.await_count
    # No row (deleted), or a failure: never raises.
    await job_tasks.search_stopped(FakeConn(), SEARCH)
    await job_tasks.search_stopped(FakeConn().on("WHERE t.job_search_id", RuntimeError("db")), SEARCH)


@pytest.mark.asyncio
async def test_the_job_chain_releases_drafts_then_tells(monkeypatch):
    calls = []
    monkeypatch.setattr(job_orchestrator, "release_drafts", AsyncMock(side_effect=lambda *a: calls.append("drafts")))
    monkeypatch.setattr(job_tasks, "search_stopped", AsyncMock(side_effect=lambda *a: calls.append("told")))
    assert job_orchestrator.JOB_CHAIN.on_terminal is job_orchestrator._stopped
    await job_orchestrator._stopped(FakeConn(), SEARCH)
    assert calls == ["drafts", "told"]


@pytest.mark.asyncio
async def test_tell_sends_the_notification(monkeypatch):
    from app.matcha.services import notification_service

    sent = AsyncMock()
    monkeypatch.setattr(notification_service, "create_notification", sent)
    task = {"id": TASK, "user_id": USER, "company_id": COMPANY, "playbook": "job_search", "status": "done",
            "title": "COO", "progress": {"note": "12 jobs"}}
    await notify.tell(FakeConn(), task)
    kwargs = sent.await_args.kwargs
    assert kwargs["title"] == "Done: COO" and kwargs["metadata"]["agent_task_id"] == str(TASK)
    sent.reset_mock()
    await notify.tell(FakeConn(), {**task, "status": "cancelled"})
    assert not sent.await_count
    assert isinstance(UUID(str(TASK)), UUID)


@pytest.mark.asyncio
async def test_web_job_metadata_marks_completion_seen_without_reading_the_full_search(conn, monkeypatch):
    full = AsyncMock()
    monkeypatch.setattr(job_service, "get_search", full)
    conn.on("WHERE t.id = $1 AND t.user_id = $2", pointer(js_status="done", js_completed_at=NOW))
    got = await service.get_task(TASK, USER, job_summary=True)
    assert got["status"] == "done" and got["unseen"] is False
    assert "items" not in got and "job_search" not in got
    # The search's own fingerprint, which /status reports, so polling it doesn't see a change every tick.
    searched = search_row(status="done", updated_at=NOW, progress='{"note": "Searching"}')
    assert got["fingerprint"] == job_service.fingerprint(searched)
    assert got["fingerprint"] != service.fingerprint(pointer(js_status="done", js_completed_at=NOW))
    assert conn.ran("SET seen_at = NOW()")
    full.assert_not_awaited()
    conn.calls.clear()
    conn.on("WHERE t.id = $1 AND t.user_id = $2", pointer())
    await service.get_task(TASK, USER, job_summary=True)
    assert not conn.ran("SET seen_at")
    await service.get_task(TASK, USER, job_summary=True, mark_seen=False)
    assert not conn.ran("SET seen_at")
    for over in ({"js_status": None}, {"js_deleted_at": NOW}):
        conn.on("WHERE t.id = $1 AND t.user_id = $2", pointer(**over))
        with pytest.raises(service.AgentTaskError) as exc:
            await service.get_task(TASK, USER, job_summary=True)
        assert exc.value.code == 404
