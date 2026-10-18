"""The research phases that call a model, with the model faked."""
import json
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_runtime import chain, inputs, runner
from app.matcha.services.matcha_work.agent_runtime.chain import Guard, PhaseFailed
from app.matcha.services.matcha_work.agent_runtime.context import RunState
from app.matcha.services.matcha_work.agent_tasks import items as items_mod, model_run, orchestrator
from app.matcha.services.matcha_work.agent_tasks.research import model_phases as M, phases
from tests.agent_runtime.helpers import FakeConn, connection, context

from ._fixtures import ITEM, TASK, TODAY, TOKEN, item_row, round_row, task_row


@pytest.fixture
def conn(monkeypatch):
    c = FakeConn()
    for module in (M, phases, chain):
        monkeypatch.setattr(module, "connection_or_direct", connection(c))
    c.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", lambda row_id, want, limit: want)
    return c


def _guard():
    return Guard(orchestrator.TASK_CHAIN, TASK, TOKEN)


def _deps(**over):
    return replace(phases.Deps(), **{"today": lambda: TODAY, "browser_ready": lambda: False, **over})


def _model(monkeypatch, result=None, *, error=False, drive=None):
    """Fake one model run: the contract's own check runs on `result`."""
    seen = []

    async def run(task, **kwargs):
        seen.append(kwargs)
        if drive:
            await drive(kwargs)
        if error:
            raise runner.AgentRunError("no luck")
        state = RunState(started=time.monotonic())
        state.provenance.update(kwargs.get("_citable", set()))
        out, _ = kwargs["contract"].normalize({"result": result}, kwargs.get("_state") or state)
        return SimpleNamespace(result=out)

    monkeypatch.setattr(model_run, "run_model_phase", run)
    return seen


# ── plan ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plan_saves_the_models_plan_or_falls_back(conn, monkeypatch):
    seen = _model(monkeypatch, {"title": "1bd SF", "item_kind": "listing", "source": "web", "queries": ["1br dogs"],
                                "fields": ["price"], "constraints": [], "preferences": [], "fit_weight": 0.4,
                                "prefer_sources": [], "summary": "x"})
    out = await M.plan(task_row(), _deps(), _guard())
    assert out.phase == phases.PROVIDERS
    [save] = conn.ran("SET plan = $3::jsonb")
    saved = json.loads(save[2][2])
    assert saved["queries"] == ["1br dogs San Francisco"] and saved["constraints"][0]["source"] == "brief"
    assert seen[0]["first_input"] is None and "2026-10-14" in seen[0]["instructions"]
    conn.calls.clear()
    _model(monkeypatch, error=True)
    await M.plan(task_row(title=""), _deps(), _guard())
    fallback = json.loads(conn.ran("SET plan = $3::jsonb")[0][2][2])
    assert fallback["origin"] == "fallback" and conn.ran("SET plan = $3::jsonb")[0][2][3].startswith("find me")


@pytest.mark.asyncio
async def test_the_persons_files_go_to_the_model(conn, monkeypatch):
    conn.on("FROM mw_agent_inputs WHERE id = ANY", [{"id": ITEM, "kind": "image"}])
    parts = AsyncMock(return_value=("Files: a.png", [{"type": "input_image"}]))
    monkeypatch.setattr(inputs, "model_parts", parts)
    seen = _model(monkeypatch, error=True)
    await M.plan(task_row(input_ids=[ITEM]), _deps(), _guard())
    content = seen[0]["first_input"][0]["content"]
    assert content[1]["text"] == "Files: a.png" and content[2] == {"type": "input_image"}
    assert await M._files(task_row()) == (None, [])
    conn.on("FROM mw_agent_inputs WHERE id = ANY", [])
    assert await M._files(task_row(input_ids=[ITEM])) == (None, [])
    assert M._first_input("x", (None, [])) is None


# ── discover ─────────────────────────────────────────────────────────────────

def _found(**over):
    return {"title": "Sunny 1BR", "subtitle": "Mission", "url": "https://apts.test/1", "image_url": None,
            "facts": [{"field": "price", "value": 3200, "quote": "Rent is $3,200 a month",
                       "source_url": "https://apts.test/1"}], **over}


@pytest.mark.asyncio
async def test_discover_keeps_what_the_run_saw(conn, monkeypatch):
    insert = AsyncMock(return_value=1)
    monkeypatch.setattr(items_mod, "insert_items", insert)
    conn.on("FROM mw_agent_task_rounds WHERE task_id = $1 AND n = $2", round_row(items_added=0))
    conn.on("COUNT(*) FROM mw_agent_task_items", 1)
    fetch = AsyncMock(return_value=({"url": "https://apts.test/1", "title": "Sunny",
                                     "text": "Rent is $3,200 a month", "products": []}, {"https://apts.test/1"}))
    state = RunState(started=time.monotonic())

    async def drive(kwargs):
        tool = next(t for t in kwargs["abilities"][0].tools if t.name == "fetch_page")
        out = await tool.handler(context(), state, {"url": "https://apts.test/1"}, 30.0)
        state.provenance.update(out.provenance)
        kwargs["_state"] = state

    seen = _model(monkeypatch, {"candidates": [_found(), _found(title="Ghost", url="https://never.test")],
                                "notes": ""}, drive=drive)
    out = await M.discover(task_row(phase_cursor="{}"), _deps(fetch_page=fetch), _guard())
    assert out.phase == phases.DISCOVER and out.cursor["web_runs"] == 1  # found some; one more run allowed
    [record] = insert.await_args.args[4]
    assert record["fields"]["price"]["status"] == "verified" and insert.await_args.kwargs["room"] == 79
    assert len(seen[0]["abilities"]) == 1
    refunds = conn.ran("SET fetch_calls = GREATEST(fetch_calls - $2, 0)")
    assert refunds[0][2][1] == 9  # granted 10, used 1


@pytest.mark.asyncio
async def test_discover_stops_when_enough_or_nothing(conn, monkeypatch):
    insert = AsyncMock(return_value=0)
    monkeypatch.setattr(items_mod, "insert_items", insert)
    conn.on("FROM mw_agent_task_rounds WHERE task_id = $1 AND n = $2", round_row(items_added=0))
    conn.on("COUNT(*) FROM mw_agent_task_items", 0)
    _model(monkeypatch, error=True)
    with pytest.raises(PhaseFailed):
        await M.discover(task_row(phase_cursor=json.dumps({"web_runs": 1})), _deps(), _guard())
    conn.on("COUNT(*) FROM mw_agent_task_items", 4)
    insert.reset_mock()
    # The provider found plenty: straight on to reading pages.
    out = await M.discover(task_row(phase_cursor=json.dumps({"provider_added": 20})), _deps(), _guard())
    assert out.phase == phases.ENRICH and insert.await_count == 0
    # "Search more" that found nothing new: rank and say so.
    conn.on("AND id = ANY($2::uuid[])", [{"title": "Sunny 1BR"}])
    seen = _model(monkeypatch, {"candidates": [], "notes": ""})
    out = await M.discover(task_row(phase_cursor=json.dumps({"more": True, "like": [str(ITEM)]})),
                           _deps(browser_ready=lambda: True), _guard())
    assert out.phase == phases.RANK and out.cursor["note"] == "Nothing new turned up."
    assert "More like these: Sunny 1BR" in seen[0]["user_text"] and len(seen[0]["abilities"]) == 2


@pytest.mark.asyncio
async def test_the_view_page_wrapper_records_what_it_read(conn, monkeypatch):
    monkeypatch.setattr(items_mod, "insert_items", AsyncMock(return_value=0))
    conn.on("FROM mw_agent_task_rounds WHERE task_id = $1 AND n = $2", round_row(items_added=0))
    conn.on("COUNT(*) FROM mw_agent_task_items", 3)
    view = AsyncMock(return_value={"url": "https://apts.test/2", "title": "Loft", "text": "Rent is $2,900 a month",
                                   "screenshot_url": None})

    async def drive(kwargs):
        tool = kwargs["abilities"][1].tools[0]
        await tool.handler(context(), RunState(started=time.monotonic()), {"url": "https://apts.test/2"}, 60.0)

    _model(monkeypatch, {"candidates": [], "notes": ""}, drive=drive)
    await M.discover(task_row(phase_cursor="{}"), _deps(view=view, browser_ready=lambda: True), _guard())
    view.assert_awaited_once()
    assert conn.ran("SET browser_views = GREATEST(browser_views - $2, 0)")[0][2][1] == 1


# ── screen ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_screen_marks_fit_and_irrelevance(conn, monkeypatch):
    other = uuid4()
    conn.on("screened_at IS NULL AND status <> 'unavailable'\n                ORDER BY", [item_row(), item_row(id=other)])
    _model(monkeypatch, {"verdicts": [{"id": "F1", "relevant": True, "fit": 4, "reasons": ["Near BART"]},
                                      {"id": "F2", "relevant": False, "fit": 0, "reasons": ["A studio"]}]})
    out = await M.screen(task_row(), _deps(), _guard())
    assert out.phase == phases.RANK
    [update] = conn.ran("fit_score = v.fit")
    assert update[2][3] == [True, False] and update[2][4] == [4, 0]
    _model(monkeypatch, error=True)
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND screened_at IS NULL", 3)
    out = await M.screen(task_row(), _deps(), _guard())
    assert out.phase == phases.SCREEN and conn.ran("fit_score = v.fit")[-1][2][3] == [True, True]
    conn.on("screened_at IS NULL AND status <> 'unavailable'\n                ORDER BY", [])
    assert (await M.screen(task_row(), _deps(), _guard())).phase == phases.RANK


# ── summarize ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summarize_writes_the_rounds_summary(conn, monkeypatch):
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 ", 3)
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND rank_band < 9", 1)
    conn.on("SELECT url FROM mw_agent_task_items", [{"url": "https://apts.test/1"}, {"url": None}])
    conn.on("ORDER BY rank LIMIT", [item_row()])
    _model(monkeypatch, {"headline": "One 1BR that takes dogs", "summary": "At $3,200 a month.", "sections": [],
                         "top": [{"id": "F1", "why": "Cheapest"}]})
    out = await M.summarize(task_row(), _deps(), _guard())
    assert out.status == "done" and out.progress == {"note": "One 1BR that takes dogs", "found": 3, "shown": 1}
    saved = json.loads(conn.ran("UPDATE mw_agent_task_rounds SET summary")[0][2][3])
    assert saved["origin"] == "model" and saved["counts"] == {"found": 3, "shown": 1, "hidden": 2}
    assert saved["top"] == [{"item_id": str(ITEM), "why": "Cheapest"}]
    _model(monkeypatch, error=True)
    out = await M.summarize(task_row(phase_cursor=json.dumps({"round_failed": "x", "note": "n"})), _deps(), _guard())
    assert out.cursor == {"round_failed": "x"}
    saved = json.loads(conn.ran("UPDATE mw_agent_task_rounds SET summary")[-1][2][3])
    assert saved["origin"] == "ranking" and saved["summary"] == "n" and saved["top"][0]["why"] == "Close to transit"


def test_a_summary_gets_two_repairs():
    assert (M.SUMMARY_LIMITS.max_model_calls, M.SUMMARY_LIMITS.max_repairs) == (3, 2)


def test_the_top_picks_are_filled_from_the_ranking():
    shown = [{"id": n, "fit_reasons": [f"why {n}"]} for n in "abcdefg"]
    assert [p["item_id"] for p in M.fill_top([{"item_id": "c", "why": "best"}], shown)] == ["c", "a", "b", "d", "e"]
    assert M.fill_top([], shown[:2]) == [{"item_id": "a", "why": "why a"}, {"item_id": "b", "why": "why b"}]
    assert M.fill_top([], [{"id": "z"}])[0]["why"] == ""


def test_fallback_summary_wording():
    assert M.fallback_summary([], total=0, hidden=0, note=None)["headline"] == "Nothing found"
    assert M.fallback_summary([], total=4, hidden=4, note=None)["summary"].startswith("4 were hidden")
    shown = [{"id": "a", "fit_reasons": []}, {"id": "b"}]
    assert M.fallback_summary(shown, total=2, hidden=0, note=None)["headline"] == "Found 2"
    assert M.fallback_summary(shown, total=9, hidden=7, note=None)["headline"] == "2 that fit, of 9 found"
    # Shown is the best ten at most; the count is what fit.
    assert M.fallback_summary(shown * 5, total=30, hidden=0, note=None)["headline"] == "Found 30"
    assert M.fallback_summary(shown * 5, total=30, hidden=4, note=None)["headline"] == "26 that fit, of 30 found"


# ── refine ───────────────────────────────────────────────────────────────────

def _refined(**over):
    return {"constraints": [{"field": "pets", "op": "includes", "value": ["dogs"]}], "preferences": [],
            "fields_add": [], "queries": [], "search_again": False, "note": "Mission only", **over}


@pytest.fixture
def refining(conn, monkeypatch):
    conn.on("FROM mw_agent_task_rounds WHERE task_id = $1 AND n = $2", round_row(kind="refine", directive="Mission only"))
    conn.on("RETURNING 1", 1)
    monkeypatch.setattr(M, "rerank", AsyncMock(return_value=8))
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND rank_band < 9", 8)
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 ", 8)
    return conn


@pytest.mark.asyncio
async def test_refine_goes_to_the_summary_when_nothing_new_is_needed(refining, monkeypatch):
    _model(monkeypatch, _refined())
    out = await M.refine(task_row(), _deps(), _guard())
    assert out.phase == phases.FILL and out.cursor == {"note": "Mission only"}
    M.rerank.assert_awaited_once()


@pytest.mark.asyncio
async def test_refine_copies_floor_plans_for_homes_that_fit_only_now(refining, monkeypatch):
    _model(monkeypatch, _refined())
    fill = AsyncMock()
    monkeypatch.setattr(M, "fill_plans", fill)
    out = await M.refine(task_row(), _deps(), _guard())
    assert out.phase == phases.FILL
    assert _refined()["constraints"][0] in fill.await_args.args[1]["constraints"]  # the plan as changed
    # Copying them is a nicety: a failure never fails the refine.
    fill.side_effect = RuntimeError("s3 down")
    assert (await M.refine(task_row(), _deps(), _guard())).phase == phases.FILL


@pytest.mark.asyncio
async def test_refine_rereads_pages_for_a_new_fact(refining, monkeypatch):
    refining.on("ORDER BY rank LIMIT", [item_row(), item_row(id=uuid4(), url="https://www.google.com/maps/x")])
    _model(monkeypatch, _refined(fields_add=["amenities"]))
    out = await M.refine(task_row(), _deps(), _guard())
    assert out.phase == phases.ENRICH
    [reset] = refining.ran("SET enriched_at = NULL")
    assert reset[2][1] == [ITEM]


@pytest.mark.asyncio
async def test_refine_searches_again_when_too_little_is_left(refining, monkeypatch):
    refining.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND rank_band < 9", 2)
    _model(monkeypatch, _refined())
    out = await M.refine(task_row(), _deps(), _guard())
    assert out.phase == phases.PROVIDERS and out.cursor["refine"] is True


@pytest.mark.asyncio
async def test_a_refine_it_cant_read_is_free(refining, monkeypatch):
    _model(monkeypatch, error=True)
    out = await M.refine(task_row(), _deps(), _guard())
    assert out.status == "done" and "round_failed" in out.cursor
    refining.on("RETURNING 1", None)
    _model(monkeypatch, _refined())
    assert (await M.refine(task_row(), _deps(), _guard())).phase is None


def test_needs_reading():
    row = {"url": "https://apts.test/1", "fields": json.dumps({"pets": {"status": "verified"}})}
    assert not M._needs_reading(row, ["pets"]) and M._needs_reading(row, ["pets", "amenities"])


@pytest.mark.asyncio
async def test_a_kind_of_search_plans_as_its_kind(conn, monkeypatch):
    """An apartments task: the planner is told what it is, the person's answers
    reach it by their own labels, and the plan is fixed to its kind."""
    brief = json.dumps({"location": "San Francisco", "budget_max": 3500, "beds_min": 1, "pets": ["dogs"],
                        "move_in": "2026-11-01"})
    seen = _model(monkeypatch, {"title": "1bd", "item_kind": "product", "source": "shopping",
                                "queries": ["1 bedroom"], "fields": ["rating"], "constraints": [],
                                "preferences": [], "fit_weight": 0.4, "prefer_sources": [], "summary": ""})
    await M.plan(task_row(playbook="apartments", brief=brief), _deps(), _guard())
    assert "Kind of search: Apartments. Its item_kind and source are fixed (listing, places)." in seen[0]["instructions"]
    assert "Bedrooms (at least): 1" in seen[0]["user_text"] and "Pets: dogs" in seen[0]["user_text"]
    saved = json.loads(conn.ran("SET plan = $3::jsonb")[0][2][2])
    assert saved["item_kind"] == "listing" and saved["source"] == "places"
    assert saved["fields"][:3] == ["price", "specials", "beds"] and "rating" in saved["fields"]
    limits = {(c["field"], c["op"]) for c in saved["constraints"] if c["source"] == "brief"}
    assert limits == {("price", "lte"), ("beds", "gte"), ("pets", "includes"), ("available_date", "before")}
