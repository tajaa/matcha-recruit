"""The model phases end to end through the real runner, with a scripted model."""
import json
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.matcha.services.matcha_work.agent_runtime import chain, phase_run, runner
from app.matcha.services.matcha_work.job_search import agent_phase, model_phases, phases
from tests.agent_runtime.helpers import FakeClient, FakeConn, call, connection, response, wire_store

from ._fixtures import SEARCH, TOKEN, search_row


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    # The run row, mark_run and the token charge are agent_runtime.phase_run's;
    # the guard's writes are agent_runtime.chain's. Patch where they run.
    for module in (model_phases, agent_phase, phases, phase_run, chain):
        monkeypatch.setattr(module, "connection_or_direct", connection(conn))
    from app.matcha.services.matcha_work.job_search import service

    monkeypatch.setattr(service, "connection_or_direct", connection(conn))
    wire_store(monkeypatch)
    monkeypatch.setattr(phase_run.store, "mark_run", AsyncMock())
    from app.matcha.services.billing import token_budget_service

    monkeypatch.setattr(token_budget_service, "deduct_tokens", AsyncMock())
    conn.on("INSERT INTO mw_project_agent_runs", uuid4())
    return conn


def guard():
    return phases.Guard(SEARCH, TOKEN)


def deps(*responses, fetch_page=None):
    client = FakeClient(list(responses))
    return phases.Deps(client=lambda _model: client, fetch_page=fetch_page or AsyncMock()), client


def finish(result):
    return response(call("finish", {"result": result}))


@pytest.mark.asyncio
async def test_run_model_phase_audits_and_charges(conn):
    d, client = deps(finish({"titles": ["COO"], "deal_breakers": [], "profile_summary": "", "weights": None}))
    out = await model_phases.plan(search_row(status="planning", model="gpt-5.6-luna"), d, guard())
    assert out.status == "discovering"
    [insert] = conn.ran("INSERT INTO mw_project_agent_runs")
    assert "'job_search'" in insert[1] and insert[2][-1] == SEARCH and insert[2][2] == f"plan:{SEARCH}"
    assert client.calls[0]["feature"] == agent_phase.USAGE_FEATURE
    assert client.calls[0]["store"] is False  # the ask and résumé are not stored by the provider
    phase_run.store.mark_run.assert_awaited_once()
    assert phase_run.store.mark_run.await_args.kwargs["status"] == "done"
    assert conn.ran("model_runs = model_runs + 1")[0][2] == (SEARCH, 12)


@pytest.mark.asyncio
async def test_a_failed_run_is_marked_and_raised(conn):
    d, _client = deps(response(text="no tool"), response(text="still no tool"))
    with pytest.raises(runner.AgentRunError):
        await agent_phase.run_model_phase(
            search_row(), phase="screen", abilities=(),
            contract=runner.ResultContract(finish=model_phases.contracts.SCREEN_FINISH,
                                           normalize=lambda a, s: ({}, [])),
            instructions="x", user_text="y", limits=model_phases.PLAN_LIMITS,
            progress=agent_phase.SearchProgress(note_fn=AsyncMock()), client_factory=d.client,
        )
    assert phase_run.store.mark_run.await_args.kwargs["status"] == "failed"


@pytest.mark.asyncio
async def test_a_search_keeps_an_offered_model_and_restamps_one_that_is_not(conn, monkeypatch):
    # conftest blanks the Anthropic key: Luna is the one model offered.
    assert await agent_phase.model_for(search_row(model="gpt-5.6-luna")) == "gpt-5.6-luna"
    assert conn.ran("UPDATE mw_job_searches") == []
    from app.core.services import anthropic_messages

    monkeypatch.setattr(anthropic_messages, "surface_model", AsyncMock(return_value="gpt-5.6-luna"))
    assert await agent_phase.model_for(search_row(model="retired-model")) == "gpt-5.6-luna"
    anthropic_messages.surface_model.assert_awaited_with("espresso.job_search")
    assert conn.ran("UPDATE mw_job_searches SET model")[0][2] == (SEARCH, "gpt-5.6-luna")


@pytest.mark.asyncio
async def test_progress_notes_are_throttled():
    note = AsyncMock()
    progress = agent_phase.SearchProgress(note_fn=note)
    await progress.note("one")
    await progress.note("two")
    await progress.note("three", force=True)
    assert [c.args[0] for c in note.await_args_list] == ["one", "three"]
    note.side_effect = RuntimeError("db")
    await progress.note("four", force=True)  # never raises
    assert await progress.step(1, "read", "x", "ok") is None


@pytest.mark.asyncio
async def test_plan_keeps_what_they_typed_and_applies_weights(conn):
    d, _ = deps(finish({"titles": ["President and COO", "coo"], "deal_breakers": [], "profile_summary": "Operator",
                        "weights": {"base": 1, "bonus": 1, "equity": 1, "fit": 0.2}}))
    search = search_row(status="planning", criteria=json.dumps({"titles": ["COO", "Chief of Staff"],
                                                                "locations": ["Austin, TX"]}))
    out = await model_phases.plan(search, d, guard())
    [write] = conn.ran("SET plan = $3::jsonb")
    plan = json.loads(write[2][2])
    # What they typed first: the board and web searches take the first titles.
    assert plan["titles"] == ["COO", "Chief of Staff", "President and COO"]
    assert json.loads(write[2][3]) == {"base": 1.0, "bonus": 1.0, "equity": 1.0, "fit": 0.2}
    assert out.progress == {"note": "Searching employers' job boards for COO, Chief of Staff, President and COO…",
                            "titles": 3}


@pytest.mark.asyncio
async def test_plan_falls_back_to_the_criteria(conn):
    d, _ = deps(response(text="?"), response(text="?"))
    out = await model_phases.plan(search_row(status="planning", criteria=json.dumps({"titles": ["COO"]})), d, guard())
    assert out.status == "discovering"
    plan = json.loads(conn.ran("SET plan = $3::jsonb")[0][2][2])
    assert plan == {"titles": ["COO"], "source": "criteria"} and conn.ran("SET plan = $3::jsonb")[0][2][3] is None


def lead_row(i, **over):
    return {"id": UUID(int=i), "title": "COO", "company": f"Co{i}", "location": "Austin, TX", "remote": False,
            "posted_text": "1 day ago", "comp": "{}", "description": "Run ops " * 200, "source_url": None,
            "ats": "{}", "pay_law_hint": None, **over}


@pytest.mark.asyncio
async def test_screen_writes_verdicts_and_moves_on(conn):
    conn.on("screen_status = 'pending'\n                ORDER BY", [lead_row(1), lead_row(2)])
    conn.on("COUNT(*) FROM mw_job_leads WHERE search_id = $1 AND screen_status = 'pending'", 0)
    conn.on("screen_status = 'relevant'", 1)
    d, client = deps(finish({"verdicts": [
        {"id": "J1", "relevant": True, "fit": 4, "reasons": ["Right level"], "deal_breaker": None},
        {"id": "J2", "relevant": False, "fit": 1, "reasons": ["Wrong function"], "deal_breaker": None}]}))
    out = await model_phases.screen(search_row(status="screening"), d, guard())
    assert out.status == "enriching" and out.progress["relevant"] == 1
    sent = client.calls[0]["input"][0]["content"][0]["text"]
    assert '"id": "J1"' in sent and str(UUID(int=1)) not in sent  # short ids only
    [write] = conn.ran("SET screen_status = CASE")
    assert write[2][3] == [True, False] and write[2][4] == [4, 1] and write[2][1] == TOKEN

    conn.on("COUNT(*) FROM mw_job_leads WHERE search_id = $1 AND screen_status = 'pending'", 5)
    d, _ = deps(response(text="?"), response(text="?"))
    out = await model_phases.screen(search_row(status="screening"), d, guard())
    assert out.status == "screening"
    assert conn.ran("SET screen_status = CASE")[-1][2][3] == [True, True]  # kept in when screening fails


@pytest.mark.asyncio
async def test_a_job_the_model_skipped_is_screened_once_more(conn):
    """The contract lets a few verdicts go missing; those jobs stay pending
    for the next batch instead of counting as matches, and are kept in with
    no fit only when skipped a second time."""
    rows = [lead_row(i) for i in range(1, 6)]
    conn.on("screen_status = 'pending'\n                ORDER BY", rows)
    conn.on("COUNT(*) FROM mw_job_leads WHERE search_id = $1 AND screen_status = 'pending'", 1)
    # J5 is missing: one of five is within what the contract lets go.
    verdicts = {"verdicts": [
        {"id": f"J{i}", "relevant": i != 2, "fit": 4, "reasons": [], "deal_breaker": None} for i in range(1, 5)]}
    out = await model_phases.screen(search_row(status="screening"), deps(finish(verdicts))[0], guard())
    assert out.status == "screening" and out.cursor == {"rescreen": [str(UUID(int=5))]}
    [write] = conn.ran("SET screen_status = CASE")
    assert write[2][2] == [UUID(int=i) for i in range(1, 5)]  # J5 is not written: it stays pending
    # Skipped again, it is kept in (relevant, unrated), as a failed batch's jobs are.
    conn.calls.clear()
    again = search_row(status="screening", phase_cursor=json.dumps({"rescreen": [str(UUID(int=5))]}))
    conn.on("COUNT(*) FROM mw_job_leads WHERE search_id = $1 AND screen_status = 'pending'", 0)
    out = await model_phases.screen(again, deps(finish(verdicts))[0], guard())
    assert out.status == "enriching" and out.cursor == {}
    [write] = conn.ran("SET screen_status = CASE")
    assert write[2][2] == [UUID(int=i) for i in range(1, 6)] and write[2][3] == [True, False, True, True, True]
    assert write[2][4][-1] is None


@pytest.mark.asyncio
async def test_screen_with_nothing_pending(conn):
    out = await model_phases.screen(search_row(status="screening"), deps()[0], guard())
    assert out.status == "enriching"


@pytest.mark.asyncio
async def test_approach_drafts_a_batch_and_queues_the_rest(conn, monkeypatch):
    monkeypatch.setattr(model_phases, "load_resume_for_model", AsyncMock(return_value="15 years in ops"))
    ids = [str(UUID(int=i)) for i in (1, 2, 3)]
    rows = [lead_row(1, ats=json.dumps({"questions": [{"key": "q1", "label": "Why us?", "kind": "open"}]}),
                     comp=json.dumps({"base": {"status": "posted", "annual_min": 2e5, "annual_max": 2.5e5,
                                               "currency": "USD", "evidence": {"quote": "$200K-$250K"}}})),
            lead_row(2)]
    conn.on("source_url, comp, ats, description, pay_law_hint", rows)
    page_url = "https://co1.test/team"

    async def fetch_page(url):
        return {"url": page_url, "title": "Team", "text": "Dana Ruiz, CEO"}, {page_url}

    d, client = deps(
        response(call("fetch_page", {"url": page_url})),
        finish({"approaches": [
            {"id": "J1", "summary": "Write to Dana.", "channel": "hiring_manager", "steps": ["Apply"],
             "talking_points": [], "negotiation": [], "cover_letter": "Dear Co1", "sources": [page_url],
             "contacts": [{"name": "Dana Ruiz", "role": "CEO", "source_url": page_url}],
             "outreach": {"to_email": None, "subject": "COO", "body": "Hi Dana"},
             "answers": [{"question_key": "q1", "question": "Why us?", "answer": "Because"}]},
        ]}),
        fetch_page=fetch_page,
    )
    search = search_row(status="approaching", use_resume=True, phase_cursor=json.dumps({"approach_queue": ids}))
    out = await model_phases.approach(search, d, guard())
    assert out.status == "approaching" and out.cursor == {"approach_queue": ids[2:]}
    sent = client.calls[0]["input"][0]["content"][0]["text"]
    assert "15 years in ops" in sent and "$200K-$250K" in sent and '"key": "q1"' in sent
    [write] = conn.ran("SET approach = COALESCE")
    drafted = [json.loads(a) if a else None for a in write[2][3]]
    assert drafted[0]["contacts"][0]["name"] == "Dana Ruiz" and drafted[0]["answers"][0]["question_key"] == "q1"
    assert drafted[1] is None  # J2 got nothing: marked failed, can be redrafted
    # `drafting` is written under the token: after a cancel released the queue,
    # a late write would otherwise leave the job drafting for good.
    [(_m, drafting, args)] = conn.ran("SET approach_status = 'drafting'")
    assert "dispatch_token = $3" in drafting and args[2] == TOKEN

    out = await model_phases.approach(search_row(status="approaching", phase_cursor="{}"), d, guard())
    assert out.status == "done"


@pytest.mark.asyncio
async def test_a_cancelled_search_goes_back_to_cancelled_after_its_draft(conn):
    """A redraft on a cancelled search ends `cancelled`, not `done`, and a
    longer queue carries that through each task."""
    def failing():
        return deps(*[response(text="?")] * 10)[0]

    conn.on("source_url, comp, ats, description, pay_law_hint", [lead_row(1), lead_row(2)])
    ids = [str(UUID(int=i)) for i in (1, 2, 3)]
    cursor = json.dumps({"approach_queue": ids, "after": "cancelled"})
    out = await model_phases.approach(search_row(status="approaching", phase_cursor=cursor), failing(), guard())
    assert out.status == "approaching" and out.cursor == {"approach_queue": ids[2:], "after": "cancelled"}
    last = json.dumps({"approach_queue": ids[2:], "after": "cancelled"})
    out = await model_phases.approach(search_row(status="approaching", phase_cursor=last), failing(), guard())
    assert out.status == "cancelled" and out.cursor == {}
    assert not conn.ran("COUNT(*) FILTER (WHERE approach_status = 'done')")  # no note to count for
    empty = json.dumps({"approach_queue": [], "after": "cancelled"})
    assert (await model_phases.approach(search_row(phase_cursor=empty), failing(), guard())).status == "cancelled"
    done = json.dumps({"approach_queue": [], "after": "done"})
    assert (await model_phases.approach(search_row(phase_cursor=done), failing(), guard())).status == "done"


@pytest.mark.asyncio
async def test_approach_failure_marks_the_batch_failed(conn):
    conn.on("source_url, comp, ats, description, pay_law_hint", [lead_row(1)])
    d, _ = deps(*[response(text="?")] * 10)
    search = search_row(status="approaching", phase_cursor=json.dumps({"approach_queue": [str(UUID(int=1))]}))
    conn.on("COUNT(*) FILTER (WHERE approach_status = 'done')", {"done": 0, "failed": 1})
    out = await model_phases.approach(search, d, guard())
    assert out.status == "done"
    assert conn.ran("SET approach = COALESCE")[0][2][3] == [None]
    assert out.progress["note"] == "Done: ranked. The approaches couldn't be drafted; Redraft a job to try again."


@pytest.mark.asyncio
async def test_the_last_note_counts_the_drafts(conn):
    empty = search_row(status="approaching", phase_cursor=json.dumps({"approach_queue": [str(UUID(int=1))]}))
    d, _ = deps(*[response(text="?")] * 10)
    for counts, note in (
        (None, "Done: ranked."),
        ({"done": 0, "failed": 0}, "Done: ranked."),  # the queued jobs were gone: nothing drafted
        ({"done": 8, "failed": 0}, "Done: ranked, with approaches drafted."),
        ({"done": 5, "failed": 3}, "Done: ranked, with 5 of 8 approaches drafted; Redraft the others to try again."),
    ):
        conn.on("COUNT(*) FILTER (WHERE approach_status = 'done')", counts)
        assert (await model_phases.approach(empty, d, guard())).progress["note"] == note


@pytest.mark.asyncio
async def test_resume_for_the_model(conn):
    from app.matcha.services.matcha_work.job_search import service

    assert await service.load_resume_for_model(uuid4()) is None
    conn.on("FROM user_resumes", {"raw_text": "Full résumé text", "parsed_data": json.dumps(
        {"current_title": "VP Operations", "experience_years": 15, "skills": ["Ops", "P&L"]})})
    text = await service.load_resume_for_model(uuid4())
    assert text.startswith("Current title: VP Operations") and "Skills: Ops, P&L" in text
    assert text.endswith("Full résumé text")
    conn.on("FROM user_resumes", {"raw_text": None, "parsed_data": "{}"})
    assert await service.load_resume_for_model(uuid4()) is None
