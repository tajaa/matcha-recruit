"""The fit floor: the first pass reads, ranks and drafts the 4/5 and 5/5 jobs;
widening adds the 3/5 ones, once, without drafting."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import pytest

from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.job_search import enqueue, phases, ranking, service
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import SEARCH, TOKEN, USER, search_row

LEADS = "AND enriched_at IS NULL AND screen_status <> 'irrelevant' AND (fit_score IS NULL OR fit_score >= $2)\n"
STRONG = "SELECT EXISTS (SELECT 1 FROM mw_job_leads"
FLOOR_WRITE = "SET progress = progress || $2::jsonb"


@pytest.mark.parametrize("progress, floor", [
    ('{"note": "Done"}', None), ('{"fit_floor": 4}', 4), ('{"fit_floor": 3}', 3),
    ('{"fit_floor": 2}', None), ('{"fit_floor": "4"}', None), ("[]", None), (None, None),
])
def test_fit_floor_reads_only_the_two_floors(progress, floor):
    assert service.fit_floor(search_row(progress=progress)) == floor
    assert service.search_view(search_row(progress=progress))["fit_floor"] == floor


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(phases, "connection_or_direct", connection(conn))
    monkeypatch.setattr(chain, "connection_or_direct", connection(conn))
    monkeypatch.setattr(phases, "rerank", AsyncMock(return_value=3))
    conn.on("SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $2", 1)
    conn.on("COUNT(*) FILTER", {"total": 93, "posted": 20, "matches": 12, "wider": 30})
    return conn


def enriching(**over):
    return search_row(status="enriching", fetch_calls=phases.MAX_FETCHES, **over)


@pytest.mark.asyncio
@pytest.mark.parametrize("strong, floor, said", [
    (True, 4, "12 strong matches (4/5 or better) of 93 jobs"),
    (False, 3, "12 matches at 3/5 or better of 93 jobs"),
])
async def test_the_first_pass_settles_the_floor(conn, strong, floor, said):
    conn.on(STRONG, strong)
    conn.on(FLOOR_WRITE, enriching(progress=json.dumps({"fit_floor": floor})))
    conn.on("SET approach_status = 'queued'", [{"id": SEARCH, "rank": 1}])
    out = await phases.enrich(enriching(), phases.Deps(), phases.Guard(SEARCH, TOKEN))
    assert conn.ran(STRONG)[0][2] == (SEARCH, ranking.FIT_FLOOR)
    assert conn.ran("ORDER BY fit_score DESC")[0][2] == (SEARCH, floor)
    [write] = conn.ran(FLOOR_WRITE)
    assert json.loads(write[2][1]) == {"fit_floor": floor} and write[2][2] == TOKEN
    phases.rerank.assert_awaited_once()
    assert out.status == "approaching" and out.progress["fit_floor"] == floor
    assert out.progress["matches"] == 12 and out.progress["note"].startswith(said)


@pytest.mark.asyncio
async def test_a_settled_floor_is_kept_between_batches(conn):
    conn.on(LEADS, [{"id": SEARCH, "title": "COO", "company": "Acme", "apply_links": "[]",
                     "comp": "{}", "description": ""}])
    conn.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", 4)
    conn.on("SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1\n               AND enriched_at IS NULL", 5)
    out = await phases.enrich(search_row(status="enriching", fetch_calls=0, progress='{"fit_floor": 4}'),
                              phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock()),
                              phases.Guard(SEARCH, TOKEN))
    assert not conn.ran(STRONG)
    assert out.status == "enriching" and out.progress["fit_floor"] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("after", ["done", "cancelled"])
async def test_widening_reads_the_3_of_5_jobs_and_drafts_nothing(conn, after):
    search = enriching(progress='{"fit_floor": 3}', phase_cursor=json.dumps({"after": after, "widen": True}))
    conn.on(FLOOR_WRITE, search)
    out = await phases.enrich(search, phases.Deps(), phases.Guard(SEARCH, TOKEN))
    assert conn.ran("ORDER BY fit_score DESC")[0][2] == (SEARCH, 3)
    phases.rerank.assert_awaited_once()
    assert not conn.ran("SET approach_status = 'queued'")
    assert out.status == after and out.cursor == {}
    assert out.progress["note"] == "Added 30 jobs at 3/5; 12 matches in all." and out.progress["fit_floor"] == 3


@pytest.mark.asyncio
async def test_a_search_cancelled_before_the_floor_is_written_is_left_alone(conn):
    conn.on(STRONG, True)
    out = await phases.enrich(enriching(), phases.Deps(), phases.Guard(SEARCH, TOKEN))
    assert out.status == "enriching"  # the chain finds its token retired
    phases.rerank.assert_not_awaited()
    assert not conn.ran("SET approach_status = 'queued'")


# ── widen ────────────────────────────────────────────────────────────────────

@pytest.fixture
def svc(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(service, "connection_or_direct", connection(conn))
    return conn


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["done", "cancelled"])
async def test_widen_puts_the_search_back_to_read_its_3_of_5_jobs(svc, status):
    svc.on("FOR UPDATE", search_row(status=status, progress='{"fit_floor": 4}'))
    svc.on("SET status = 'enriching'", search_row(status="enriching"))
    search, token = await service.widen(SEARCH, USER)
    assert search["status"] == "enriching"
    [update] = svc.ran("SET status = 'enriching'")
    assert update[2][1] == token
    assert json.loads(update[2][2]) == {"after": status, "widen": True}
    assert json.loads(update[2][3])["fit_floor"] == ranking.WIDER_FIT_FLOOR
    assert "redrafts" not in update[1]  # free


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [
    {"status": "screening", "progress": '{"fit_floor": 4}'},
    {"status": "failed", "progress": '{"fit_floor": 4}'},
    {"status": "done", "progress": '{"fit_floor": 3}'},  # widened already, or 3/5 from the start
    {"status": "done", "progress": '{"note": "Done"}'},  # from before the floor
])
async def test_widen_refusals(svc, over):
    svc.on("FOR UPDATE", search_row(**over))
    with pytest.raises(service.JobSearchError) as exc:
        await service.widen(SEARCH, USER)
    assert exc.value.code == 409
    assert not svc.ran("SET status = 'enriching'")


@pytest.mark.asyncio
async def test_widen_while_another_search_runs(svc):
    svc.on("FOR UPDATE", search_row(status="done", progress='{"fit_floor": 4}'))
    svc.on("SET status = 'enriching'", asyncpg.UniqueViolationError("one live"))
    with pytest.raises(service.JobSearchError) as exc:
        await service.widen(SEARCH, USER)
    assert exc.value.code == 409


@pytest.mark.asyncio
async def test_widen_dispatches_and_tolerates_a_down_broker(monkeypatch):
    monkeypatch.setattr(service, "widen", AsyncMock(return_value=({}, TOKEN)))
    monkeypatch.setattr(service, "get_search", AsyncMock(return_value={"status": "enriching"}))
    dispatch = AsyncMock()
    monkeypatch.setattr(enqueue, "dispatch", dispatch)
    user = SimpleNamespace(id=USER, role="client")
    assert await enqueue.widen(user, SEARCH) == {"status": "enriching"}
    dispatch.assert_awaited_once_with(SEARCH, TOKEN)
    dispatch.side_effect = RuntimeError("down")
    assert await enqueue.widen(user, SEARCH) == {"status": "enriching"}


@pytest.mark.asyncio
async def test_widen_route(monkeypatch):
    from app.core.models.auth import CurrentUser
    from app.matcha.routes.matcha_work import job_search as routes

    user = CurrentUser(id=USER, email="owner@example.test", role="client")
    monkeypatch.setattr(routes.enqueue, "widen", AsyncMock(return_value={"ok": True}))
    assert await routes.widen_job_search(SEARCH, user) == {"ok": True}
    assert routes.enqueue.widen.await_args.args == (user, SEARCH)
