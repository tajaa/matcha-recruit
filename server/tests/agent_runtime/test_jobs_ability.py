"""The `jobs` ability: reads the person's searches, keeps their notes, and a
block rebuilt from what the run read."""
import time
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_runtime import consent
from app.matcha.services.matcha_work.agent_runtime.abilities import jobs
from app.matcha.services.matcha_work.agent_runtime.context import RunState
from app.matcha.services.matcha_work.job_search.service import JobSearchError

from .helpers import context

SEARCH, LEAD = str(uuid4()), str(uuid4())


def lead(**over):
    return {"id": LEAD, "rank": 1, "title": "COO", "company": "Acme", "location": "Austin, TX", "remote": False,
            "comp_line": "$250K–$300K", "comp_status": "posted", "fit_score": 4, "screen_status": "relevant",
            "user_state": "new", "approach_status": "done", "apply_url": "https://boards.greenhouse.io/acme/jobs/1",
            "flags": [], "description": "x" * 9000, "rank_explain": {}, **over}


def search_view(leads):
    return {"id": SEARCH, "title": "COO", "status": "done", "lead_count": len(leads), "posted_pay_count": 1,
            "created_at": None, "error": None, "ask": "COO roles", "weights": {"base": 0.45},
            "progress": {}, "leads": leads}


@pytest.fixture
def run(monkeypatch):
    ability = jobs.build()
    state = RunState(started=time.monotonic())
    ctx = context()
    state.sessions[jobs.KEY] = ability.session_factory(ctx)
    tools = {t.name: t for t in ability.tools}

    async def call(name, **args):
        out = await tools[name].handler(ctx, state, args, 60)
        return out.payload

    return ability, state, ctx, call


def test_shape():
    ability = jobs.build()
    assert ability.private_only and ability.consent_version == consent.current_version("jobs") == "jobs-2"
    assert {t.effect for t in ability.tools} == {"read", "draft"}
    assert all(t.step_kind in ("read", "draft") for t in ability.tools)
    assert [t.name for t in ability.tools if t.untrusted_output] == ["read_job_search", "read_job_lead"]


@pytest.mark.asyncio
async def test_reading_then_updating(run, monkeypatch):
    _ability, state, ctx, call = run
    monkeypatch.setattr(jobs.store, "list_searches", AsyncMock(return_value=[search_view([])]))
    monkeypatch.setattr(jobs.store, "get_search", AsyncMock(return_value=search_view([lead()] * 30)))
    monkeypatch.setattr(jobs.store, "get_lead", AsyncMock(return_value=lead(approach={"summary": "Write to Dana"})))
    monkeypatch.setattr(jobs.store, "patch_lead", AsyncMock(return_value=lead(user_state="saved")))

    listed = await call("list_job_searches")
    assert listed["searches"][0]["id"] == SEARCH and "leads" not in listed["searches"][0]
    page = await call("read_job_search", search_id=SEARCH)
    assert len(page["jobs"]) == jobs.PAGE and page["next_offset"] == jobs.PAGE
    assert "description" not in page["jobs"][0]
    assert (await call("read_job_search", search_id=SEARCH, offset=25))["next_offset"] is None
    one = await call("read_job_lead", search_id=SEARCH, job_id=LEAD)
    assert len(one["job"]["description"]) == jobs.DESCRIPTION_CHARS and "rank_explain" not in one["job"]
    jobs.store.get_lead.assert_awaited_once()
    assert jobs.store.get_lead.await_args.args[2] == ctx.user_id

    saved = await call("update_job_lead", job_id=LEAD, status="saved", notes="Call Dana")
    assert saved["saved"] and saved["job"]["user_state"] == "saved"
    patch = jobs.store.patch_lead.await_args.args[3]
    assert (patch.user_state, patch.notes) == ("saved", "Call Dana")


@pytest.mark.asyncio
async def test_only_what_was_read_can_be_changed(run, monkeypatch):
    _ability, _state, _ctx, call = run
    monkeypatch.setattr(jobs.store, "patch_lead", AsyncMock())
    monkeypatch.setattr(jobs.store, "update_weights", AsyncMock())
    assert "Read this job" in (await call("update_job_lead", job_id=LEAD, status="applied", notes=None))["error"]
    assert "Read this search" in (await call("rank_job_search", search_id=SEARCH, base=1, bonus=0,
                                             equity=0, fit=0))["error"]
    jobs.store.patch_lead.assert_not_awaited()
    assert "id from a search" in (await call("read_job_search", search_id="not-a-uuid"))["error"]
    monkeypatch.setattr(jobs.store, "get_search", AsyncMock(side_effect=JobSearchError("Job search not found.", 404)))
    assert (await call("read_job_search", search_id=SEARCH))["error"] == "Job search not found."


@pytest.mark.asyncio
async def test_rank_with_new_weights(run, monkeypatch):
    _ability, state, _ctx, call = run
    jobs.session_of(state).searches.add(SEARCH)
    monkeypatch.setattr(jobs.store, "update_weights", AsyncMock(return_value={**search_view([lead()]),
                                                                            "weights": {"base": 1.0}}))
    out = await call("rank_job_search", search_id=SEARCH, base=1, bonus=0, equity=0, fit=0)
    assert out["weights"] == {"base": 1.0} and out["jobs"][0]["id"] == LEAD
    bad = await call("rank_job_search", search_id=SEARCH, base=0, bonus=0, equity=0, fit=0)
    assert "error" in bad


@pytest.mark.asyncio
async def test_jobs_below_the_fit_floor_are_counted_not_listed(run, monkeypatch):
    _ability, state, _ctx, call = run
    weak = [lead(id=str(uuid4()), fit_score=3, rank_band=8) for _ in range(3)]
    view = {**search_view([lead(rank_band=0)] + weak), "fit_floor": 4}
    monkeypatch.setattr(jobs.store, "get_search", AsyncMock(return_value=view))
    page = await call("read_job_search", search_id=SEARCH)
    assert [j["id"] for j in page["jobs"]] == [LEAD] and page["weaker_matches"] == 3
    assert page["search"]["fit_floor"] == 4 and page["next_offset"] is None
    wide = await call("read_job_search", search_id=SEARCH, include_weaker=True)
    assert len(wide["jobs"]) == 4 and wide["weaker_matches"] == 3
    monkeypatch.setattr(jobs.store, "update_weights", AsyncMock(return_value=view))
    ranked = await call("rank_job_search", search_id=SEARCH, base=1, bonus=0, equity=0, fit=0)
    assert [j["id"] for j in ranked["jobs"]] == [LEAD]


def test_block_is_rebuilt_from_what_was_read(run):
    ability, state, _ctx, _call = run
    jobs._remember(jobs.session_of(state), SEARCH, [lead(comp_line="$250K–$300K")])
    block, warnings = ability.gate("jobs", {"search_id": SEARCH, "job_ids": [LEAD, str(uuid4())],
                                            "comp_line": "$900K"}, state)
    assert block["type"] == "jobs" and [j["id"] for j in block["jobs"]] == [LEAD]
    assert block["jobs"][0]["comp_line"] == "$250K–$300K" and warnings == ["Dropped a job this run did not read"]
    assert ability.gate("jobs", {"search_id": str(uuid4()), "job_ids": [LEAD]}, state)[0] is None
    assert ability.gate("jobs", "junk", state)[0] is None
    empty = RunState(started=time.monotonic())
    assert ability.gate("jobs", {"search_id": SEARCH, "job_ids": [LEAD]}, empty)[0] is None


@pytest.mark.asyncio
async def test_the_assistant_reads_the_directions_a_search_suggested(run, monkeypatch):
    _ability, _state, _ctx, call = run
    direction = {"title": "Solutions Architect", "why": "You've led 20+ customer calls.", "evidence": "secret quote"}
    view = {**search_view([lead(direction="Solutions Architect"), lead(id=str(uuid4()), direction=None)]),
            "plan": {"directions": [direction]}}
    monkeypatch.setattr(jobs.store, "get_search", AsyncMock(return_value=view))
    page = await call("read_job_search", search_id=SEARCH)
    assert page["search"]["directions"] == [{"title": "Solutions Architect", "why": "You've led 20+ customer calls."}]
    assert [j["direction"] for j in page["jobs"]] == ["Solutions Architect", None]
    monkeypatch.setattr(jobs.store, "get_search", AsyncMock(return_value=search_view([lead()])))
    assert (await call("read_job_search", search_id=SEARCH))["search"]["directions"] == []
