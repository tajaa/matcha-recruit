"""Saved searches and leads: owner-scoped reads, re-ranks, cancel and the tombstone."""
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.models.matcha_work.job_search import JobWeights, LeadPatch
from app.matcha.services.matcha_work.job_search import service
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import COMPANY, LEAD, SEARCH, USER, lead_row, search_row


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(service, "connection_or_direct", connection(conn))
    return conn


@pytest.mark.asyncio
async def test_list_and_read_are_owner_scoped(conn):
    conn.on("FROM mw_job_searches s", [search_row()])
    [listed] = await service.list_searches(USER, COMPANY)
    assert listed["id"] == str(SEARCH) and listed["lead_count"] == 2
    assert listed["weights"]["base"] == 0.45  # defaults when none were stored
    assert conn.calls[-1][2] == (USER, COMPANY)

    conn.on("FROM mw_job_searches s", search_row())
    conn.on("FROM mw_job_leads WHERE search_id", [lead_row()])
    out = await service.get_search(SEARCH, USER)
    assert out["leads"][0]["comp_line"] == "$250K–$300K" and out["leads"][0]["apply_url"].startswith("https://")
    assert len(out["fingerprint"]) == 16


@pytest.mark.asyncio
async def test_someone_elses_search_is_not_found(conn):
    with pytest.raises(service.JobSearchError) as exc:
        await service.get_search(SEARCH, uuid4())
    assert exc.value.code == 404
    conn.on("FROM mw_job_searches s", search_row())
    with pytest.raises(service.JobSearchError) as exc:
        await service.get_lead(SEARCH, LEAD, USER)
    assert exc.value.code == 404


@pytest.mark.asyncio
async def test_lead_detail(conn):
    conn.on("FROM mw_job_searches s", search_row())
    conn.on("SELECT * FROM mw_job_leads WHERE id", lead_row())
    lead = await service.get_lead(SEARCH, LEAD, USER)
    assert lead["ats"] == {"provider": "greenhouse", "questions": [{"key": "q1", "label": "Why?"}]}
    assert lead["comp"]["base"]["annual_max"] == 300000 and lead["description"] == "Lead ops."


@pytest.mark.asyncio
async def test_status_restarts_a_stalled_live_search(conn, monkeypatch):
    from app.matcha.services.matcha_work.job_search import orchestrator

    nudge = AsyncMock(return_value=False)
    monkeypatch.setattr(orchestrator, "nudge", nudge)
    conn.on("FROM mw_job_searches s", search_row(status="enriching"))
    out = await service.status_view(SEARCH, USER)
    assert out["status"] == "enriching" and out["progress"] == {"note": "Done"}
    nudge.assert_awaited_once_with(SEARCH)
    conn.on("FROM mw_job_searches s", search_row(status="done"))
    await service.status_view(SEARCH, USER)
    assert nudge.await_count == 1


@pytest.mark.asyncio
async def test_dismissing_a_lead_reranks_but_notes_do_not(conn, monkeypatch):
    rerank = AsyncMock(return_value=2)
    monkeypatch.setattr(service, "rerank", rerank)
    conn.on("FOR UPDATE", search_row())
    conn.on("FROM mw_job_leads WHERE id = $1 AND search_id = $2 FOR UPDATE", lead_row())
    conn.on("UPDATE mw_job_leads SET user_state", lead_row(notes="Call Sam"))
    await service.patch_lead(SEARCH, LEAD, USER, LeadPatch(notes="Call Sam"))
    rerank.assert_not_awaited()
    conn.on("UPDATE mw_job_leads SET user_state", lead_row(user_state="dismissed"))
    # The re-read after the re-rank; the locked read (scripted last, so first) still sees "new".
    conn.on("SELECT * FROM mw_job_leads WHERE id = $1 AND search_id = $2", lead_row(user_state="dismissed"))
    conn.on("FROM mw_job_leads WHERE id = $1 AND search_id = $2 FOR UPDATE", lead_row())
    out = await service.patch_lead(SEARCH, LEAD, USER, LeadPatch(user_state="dismissed"))
    assert out["user_state"] == "dismissed"
    rerank.assert_awaited_once()
    # The re-read after the re-rank is scoped to the search too.
    assert conn.calls[-1][2] == (LEAD, SEARCH)
    update = conn.ran("UPDATE mw_job_leads SET user_state")[-1]
    assert update[2] == (LEAD, SEARCH, "dismissed", "")
    conn.on("FROM mw_job_leads WHERE id = $1 AND search_id = $2 FOR UPDATE", None)
    with pytest.raises(service.JobSearchError):
        await service.patch_lead(SEARCH, LEAD, USER, LeadPatch(notes="x"))


@pytest.mark.asyncio
async def test_new_weights_rerank_immediately(conn, monkeypatch):
    rerank = AsyncMock(return_value=2)
    monkeypatch.setattr(service, "rerank", rerank)
    conn.on("FROM mw_job_searches s", search_row())
    conn.on("FOR UPDATE", search_row())
    conn.on("UPDATE mw_job_searches SET weights", search_row(weights_source="user"))
    await service.update_weights(SEARCH, USER, JobWeights(base=1, bonus=0, equity=0, fit=0))
    update = conn.ran("UPDATE mw_job_searches SET weights")[0]
    assert json.loads(update[2][1]) == {"base": 1.0, "bonus": 0.0, "equity": 0.0, "fit": 0.0}
    rerank.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_ranks_what_was_found(conn, monkeypatch):
    rerank = AsyncMock(return_value=2)
    monkeypatch.setattr(service, "rerank", rerank)
    conn.on("FROM mw_job_searches s", search_row(status="cancelled"))
    conn.on("FOR UPDATE", search_row(status="enriching"))
    conn.on("SET status = 'cancelled'", search_row(status="cancelled"))
    await service.cancel_search(SEARCH, USER)
    assert conn.ran("SET status = 'cancelled'") and rerank.await_count == 1
    assert conn.ran("SET approach_status = 'failed'")
    conn.on("FOR UPDATE", search_row(status="done"))
    await service.cancel_search(SEARCH, USER)
    assert len(conn.ran("SET status = 'cancelled'")) == 1


@pytest.mark.asyncio
async def test_delete_leaves_a_tombstone(conn):
    conn.on("FOR UPDATE", search_row(status="discovering"))
    assert await service.delete_search(SEARCH, USER) == {"deleted": True}
    assert conn.ran("DELETE FROM mw_job_leads") and conn.ran("DELETE FROM mw_project_agent_runs")
    tomb, pointer = conn.ran("SET deleted_at = NOW()")
    assert "ask = ''" in tomb[1] and "THEN 'cancelled'" in tomb[1]
    # Its row in Tasks goes with it.
    assert "UPDATE mw_agent_tasks" in pointer[1] and pointer[2] == (SEARCH,)


@pytest.mark.asyncio
async def test_rerank_writes_every_lead_in_one_statement():
    a, b = uuid4(), uuid4()
    conn = FakeConn().on("SELECT id, comp, fit_score", [
        {"id": a, "comp": "{}", "fit_score": 4, "screen_status": "relevant", "user_state": "new", "posted_text": "1 day ago"},
        {"id": b, "comp": json.dumps({"base": {"status": "posted", "annual_min": 2e5, "annual_max": 2.2e5, "currency": "USD"}}),
         "fit_score": None, "screen_status": "pending", "user_state": "new", "posted_text": None},
    ])
    assert await service.rerank(conn, search_row()) == 2
    [write] = conn.ran("unnest(")
    ids, scores, ranks, bands = write[2][1:5]
    assert ids == [b, a] and ranks == [1, 2] and bands == [0, 2]
    assert await service.rerank(FakeConn(), search_row()) == 0


@pytest.mark.asyncio
async def test_a_stale_search_that_found_jobs_ends_done(monkeypatch):
    """The create-time sweep ends a dead search the way reconcile would: done
    and ranked when it paid for jobs (it counts), failed when it found none."""
    rerank = AsyncMock(return_value=3)
    monkeypatch.setattr(service, "rerank", rerank)
    found, empty = uuid4(), uuid4()
    conn = (FakeConn()
            .on("FOR UPDATE", [search_row(id=found, status="enriching"), search_row(id=empty, status="discovering")])
            .on("SELECT EXISTS (SELECT 1 FROM mw_job_leads", lambda search_id: search_id == found))
    assert await service.end_stale(conn, USER) == 2
    ends = {call[2][0]: call[2][1] for call in conn.ran("error = COALESCE(error, 'Stopped:")}
    assert ends == {found: "done", empty: "failed"}
    assert rerank.await_count == 1
    assert "INTERVAL '2 hours'" in conn.ran("FOR UPDATE")[0][1]


@pytest.mark.asyncio
async def test_a_stale_redraft_on_a_cancelled_search_ends_cancelled(monkeypatch):
    monkeypatch.setattr(service, "rerank", AsyncMock(return_value=3))
    cursor = json.dumps({"approach_queue": ["x"], "after": "cancelled"})
    conn = (FakeConn()
            .on("FOR UPDATE", [search_row(status="approaching", phase_cursor=cursor)])
            .on("SELECT EXISTS (SELECT 1 FROM mw_job_leads", True))
    assert await service.end_stale(conn, USER) == 1
    [end] = conn.ran("error = COALESCE(error, 'Stopped:")
    assert end[2][1] == "cancelled"


@pytest.mark.asyncio
async def test_find_by_request(conn):
    assert await service.find_by_request(USER, uuid4()) is None
    conn.on("AND request_id = $2", search_row(status="discovering"))
    assert (await service.find_by_request(USER, uuid4()))["status"] == "discovering"
