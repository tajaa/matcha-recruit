"""Ten findings at a time: the bar, release, look-ups, photos, looking further,
the suggestion, and Sonnet only when Haiku is having a hard time."""
import json
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.services.anthropic_messages import CLAUDE_HAIKU, CLAUDE_SONNET
from app.matcha.services.matcha_work import brave_search
from app.matcha.services.matcha_work.agent_runtime import chain, runner
from app.matcha.services.matcha_work.agent_runtime.chain import Guard
from app.matcha.services.matcha_work.agent_runtime.context import RunState
from app.matcha.services.matcha_work.agent_tasks import (
    chat,
    document,
    model_run,
    orchestrator,
    playbooks,
    service,
)
from app.matcha.services.matcha_work.agent_tasks.research import (
    batches,
    contracts,
    phases,
    suggest,
)
from app.matcha.services.matcha_work.agent_tasks.research import fill as fill_mod
from app.matcha.services.matcha_work.agent_tasks.research import model_phases as M
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import PLAN, TASK, TODAY, TOKEN, item_row, price, round_row, task_row

BATCHED = {**PLAN, "batches": True}
PHONE = {"value": "(415) 555-0100", "status": "verified", "display": "(415) 555-0100",
         "evidence": {"quote": "(415) 555-0100", "url": "https://apts.test/1", "origin": "provider"}}
PHOTO = [{"url": "https://cdn.test/a.webp", "page_url": "https://apts.test/1", "alt": ""}]


def ready(**over):
    """A listing with everything it needs to be shown."""
    return item_row(**{"id": uuid4(), "fields": json.dumps({"price": price(3000), "phone": PHONE}),
                       "images": json.dumps(PHOTO), **over})


@pytest.fixture
def conn(monkeypatch):
    c = FakeConn()
    for module in (M, phases, chain, fill_mod, model_run):
        monkeypatch.setattr(module, "connection_or_direct", connection(c))
    c.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", lambda row_id, want, limit: want)
    return c


def _guard():
    return Guard(orchestrator.TASK_CHAIN, TASK, TOKEN)


def _deps(**over):
    return replace(phases.Deps(), **{"today": lambda: TODAY, "browser_ready": lambda: False, **over})


# ── the bar and release ──────────────────────────────────────────────────────

def test_a_finding_is_released_only_with_what_its_kind_needs():
    assert batches.missing(ready(), "listing") == []
    bare = item_row(fields="{}", images="[]")
    assert batches.missing(bare, "listing") == ["price", "photo", "contact"]
    assert batches.missing(bare, "place") == ["photo", "contact"]
    assert batches.missing(bare, "product") == ["price", "photo"]
    assert batches.missing(bare, "other") == []
    homes = item_row(fields=json.dumps({"phone": PHONE}), images=json.dumps(PHOTO),
                     units=json.dumps([{"rent": 2900.0}]))
    assert batches.missing(homes, "listing") == []  # its homes carry the rent


def test_the_next_batch_skips_what_was_shown_and_what_isnt_ready():
    a, b, c = ready(), item_row(id=uuid4(), fields="{}"), ready()
    assert batches.pick([a, b, c], item_kind="listing") == [a, c]
    assert batches.pick([a, b, c], item_kind="listing", exclude=[str(a["id"])]) == [c]
    assert len(batches.pick([ready() for _ in range(14)], item_kind="listing")) == batches.BATCH
    assert batches.shortfall([a, b], item_kind="listing", exclude=[str(a["id"])]) == {
        "price": 1, "photo": 1, "contact": 1}


def _claimed(low, high=None, unit="month"):
    made = {**price(low, status="claimed", unit=unit, origin="search")}
    return {**made, "high": high} if high else made


def test_a_price_only_another_site_states_waits_when_it_is_over_the_limit():
    """PLAN's limit is rent at most $3,500 a month."""
    def row(entry):
        return ready(fields=json.dumps({"price": entry, "phone": PHONE}))

    over, under, own = row(_claimed(3600)), row(_claimed(3400, 3900)), row(price(3600))
    assert batches.over_limit(over, PLAN) and not batches.over_limit(under, PLAN)
    assert not batches.over_limit(own, PLAN)  # its own page's price: the ranking hides it, not this
    assert not batches.over_limit(row(_claimed(3600, unit="night")), PLAN)  # not the same kind of price
    assert not batches.over_limit(over, {"constraints": []}) and not batches.over_limit(item_row(), PLAN)
    between = {"constraints": [{"field": "price", "op": "between", "value": [2000, 3000]}]}
    assert batches.over_limit(row(_claimed(3100)), between) and batches.over_limit(row(_claimed(1500, 1900)), between)
    assert not batches.over_limit(row(_claimed(1800, 2400)), between)
    floor = {"constraints": [{"field": "price", "op": "gte", "value": 2000}]}
    assert batches.over_limit(row(_claimed(1500)), floor) and not batches.over_limit(row(_claimed(2500)), floor)
    assert batches.missing(over, "listing", PLAN) == [batches.OVER_LIMIT]
    assert batches.missing(over, "listing") == []  # no plan, no limit
    assert batches.pick([over, under], item_kind="listing", plan=PLAN) == [under]
    assert batches.shortfall([over, under], item_kind="listing", plan=PLAN) == {batches.OVER_LIMIT: 1}


def test_released_and_shown():
    a, b = str(uuid4()), str(uuid4())
    summaries = [json.dumps({"batch": [a]}), None, {"batch": [b, a]}, {"headline": "x"}, {"batch": "nope"}]
    assert batches.released(summaries) == [a, b]
    rows = [{"id": a, "user_state": "new"}, {"id": "c", "user_state": "saved"}, {"id": "d", "user_state": "new"}]
    assert batches.shown(rows, plan=BATCHED, released_ids=[a]) == rows[:2]
    assert batches.shown(rows, plan=PLAN, released_ids=[]) == rows  # planned before batches
    assert contracts.finalize_plan({}, {}, today=TODAY)["batches"] is True


def test_every_list_of_findings_shows_only_what_was_released():
    assert "t.plan->>'batches'" in batches.SHOWN_SQL and "summary->'batch'" in batches.SHOWN_SQL
    assert batches.SHOWN_SQL in service._COUNTS
    assert "summary->'batch'" in service._RELEASED_ANY
    assert playbooks.get("apartments").round_phases["more"] == "fill"


@pytest.mark.asyncio
async def test_get_task_shows_the_released_batch():
    c = FakeConn()
    shown, waiting = item_row(id=uuid4()), item_row(id=uuid4())
    c.on("WHERE t.id = $1 AND t.user_id = $2", task_row(plan=json.dumps(BATCHED)))
    c.on("FROM mw_agent_task_items WHERE task_id", [shown, waiting])
    c.on("FROM mw_agent_task_rounds WHERE task_id", [round_row(summary=json.dumps({"batch": [str(shown["id"])]}))])
    import app.matcha.services.matcha_work.agent_tasks.service as module

    original = module.connection_or_direct
    module.connection_or_direct = connection(c)
    try:
        got = await service.get_task(TASK, uuid4(), mark_seen=False)
    finally:
        module.connection_or_direct = original
    assert [i["id"] for i in got["items"]] == [str(shown["id"])]


@pytest.mark.asyncio
async def test_picks_come_from_the_rounds_batch():
    c = FakeConn()
    one = item_row(id=uuid4())
    c.on("id::text = ANY($2::text[])", [one])
    assert await chat.picked_from(c, TASK, {"batch": [str(one["id"])]}) == [one]
    assert c.calls[-1][2] == (TASK, [str(one["id"])])
    await chat.picked_from(c, TASK, {"headline": "x"})
    assert "rank_band < 9" in c.calls[-1][1]
    await document.pick_rows(c, TASK, [])
    assert "summary->'batch'" in c.calls[-1][1] and "JOIN mw_agent_tasks t" in c.calls[-1][1]


@pytest.mark.asyncio
async def test_a_more_round_costs_only_when_it_shows_more():
    c = FakeConn()
    await service.close_round(c, TASK)
    settle = c.calls[0][1]
    assert "r.kind = 'more' AND NOT" in settle and "summary->'batch'" in settle
    # A batch that came back empty is free even when the round found buildings.
    assert "r.items_added = 0 OR COALESCE(r.summary ? 'batch', false)" in settle
    assert "Nothing more could be shown." in settle


# ── Brave's pictures ─────────────────────────────────────────────────────────

def test_brave_results_carry_a_picture_only_when_asked():
    body = {"web": {"results": [
        {"title": "A", "url": "https://a.test/", "description": "x",
         "thumbnail": {"src": "https://imgs.search.brave.com/a", "original": "https://a.test/og.jpg"}},
        {"title": "B", "url": "https://b.test/", "description": "y", "thumbnail": {"src": "https://imgs.test/b", "logo": True}},
        {"title": "C", "url": "https://c.test/", "description": "z", "thumbnail": {"src": "http://plain.test/c"}},
    ]}}
    assert all("image" not in r for r in brave_search.results(body))
    with_images = brave_search.results(body, images=True)
    assert with_images[0]["image"] == "https://a.test/og.jpg"
    assert "image" not in with_images[1] and "image" not in with_images[2]


# ── look-ups ─────────────────────────────────────────────────────────────────

def test_a_result_is_about_a_finding_when_it_names_it():
    assert fill_mod.names("The George Apartments", "The George | San Francisco, CA | Apartments.com")
    assert not fill_mod.names("Canyon Lofts", "Grand Canyon tours")
    assert not fill_mod.names("The", "anything")
    assert fill_mod.query_for({"title": "The George"}, "listing", "San Francisco, CA") == \
        "The George San Francisco, CA rent"
    assert fill_mod.query_for({"title": "Blue Bottle San Francisco"}, "place", "San Francisco, CA") == \
        "Blue Bottle San Francisco"
    task = task_row(brief=json.dumps({"near": "Lady Bird Lake"}), plan=json.dumps({**PLAN, "location": None}))
    assert fill_mod.where_of(task) == "Lady Bird Lake"


def test_results_give_a_claimed_rent_a_phone_and_pictures_own_site_first():
    row = item_row(title="The George", url="https://www.thegeorgesf.test/")
    results = [
        {"title": "The George - Apartments.com", "url": "https://apts.test/george",
         "description": "1 Bed $2,950 - $3,400 per month. Call (415) 555-0199", "image": "https://apts.test/g.jpg"},
        {"title": "Home", "url": "https://thegeorgesf.test/", "description": "Luxury living",
         "image": "https://thegeorgesf.test/og.jpg"},
        {"title": "Unrelated", "url": "https://other.test/", "description": "Studios $999/mo",
         "image": "https://other.test/x.jpg"},
    ]
    got = fill_mod.read_results(row, results, item_kind="listing", today=TODAY)
    assert [i["source_url"] for i in got["image_candidates"]] == ["https://thegeorgesf.test/og.jpg",
                                                                  "https://apts.test/g.jpg"]
    rent = got["fields"]["price"]
    assert rent["status"] == "claimed" and rent["evidence"]["origin"] == "search"
    assert rent["value"] == 2950 and rent["evidence"]["url"] == "https://apts.test/george"
    assert got["fields"]["phone"]["value"] == "(415) 555-0199" and got["fields"]["phone"]["status"] == "claimed"
    assert fill_mod.read_results(row, results, item_kind="place", today=TODAY)["fields"].get("price") is None


def test_next_step():
    step = fill_mod.next_step
    assert step(round_kind="initial", cursor={}, ready=3, room=50) == phases.SUMMARIZE  # never re-searches
    assert step(round_kind="refine", cursor={}, ready=0, room=50) == phases.SUMMARIZE
    assert step(round_kind="more", cursor={}, ready=12, room=50) == phases.SUMMARIZE  # ten were waiting
    assert step(round_kind="more", cursor={}, ready=3, room=50) == phases.PROVIDERS
    assert step(round_kind="more", cursor={"like": ["x"]}, ready=12, room=50) == phases.PROVIDERS
    assert step(round_kind="more", cursor={"searched": True}, ready=3, room=50) == phases.SUMMARIZE
    assert step(round_kind="more", cursor={}, ready=3, room=0) == phases.SUMMARIZE


@pytest.mark.asyncio
async def test_fill_looks_up_and_copies_photos_then_releases(conn):
    done = ready()
    no_photo = item_row(id=uuid4(), fields=json.dumps({"price": price(3100), "phone": PHONE}), images="[]",
                        image_candidates=json.dumps([{"source_url": "https://apts.test/p.jpg",
                                                      "page_url": "https://apts.test/2", "alt": ""}]))
    bare = item_row(id=uuid4(), title="The George", url="https://thegeorgesf.test/", fields="{}", images="[]")
    conn.on("SELECT kind FROM mw_agent_task_rounds", "initial")
    conn.on("SELECT summary FROM mw_agent_task_rounds", [{"summary": json.dumps({"looked_up": [str(done["id"])]})}])
    conn.on("units, images, image_candidates, user_state", [done, no_photo, bare])
    search = AsyncMock(return_value=[{"title": "The George", "url": "https://thegeorgesf.test/",
                                      "description": "1 Bed $2,950/mo", "image": "https://thegeorgesf.test/og.jpg"}])
    rehost = AsyncMock(return_value=(PHOTO, []))
    out = await fill_mod.fill(task_row(plan=json.dumps(BATCHED)), _deps(search=search, rehost=rehost), _guard())
    assert [c.args[0] for c in search.await_args_list] == ["Sunny 1BR San Francisco rent", "The George San Francisco rent"]
    saved = {call[2][0]: json.loads(call[2][3]) for call in conn.ran("SET fields = $4::jsonb, image_candidates")}
    assert saved[bare["id"]]["price"]["status"] == "claimed"
    [photos] = conn.ran("SET images = $4::jsonb")
    assert str(photos[2][0]) == str(no_photo["id"]) and rehost.await_args.kwargs["limit"] == 2
    # Only one ready, and an initial round never searches again from here: it releases and says so.
    assert out.phase == phases.SUMMARIZE and out.cursor["look_ups"] == 2
    assert set(out.cursor["looked_up"]) == {str(i["id"]) for i in (done, no_photo, bare)}


@pytest.mark.asyncio
async def test_look_ups_stop_at_the_rounds_cap(conn):
    rows = [item_row(id=uuid4(), title=f"Building {n}", fields="{}", images="[]") for n in range(20)]
    conn.on("SELECT kind FROM mw_agent_task_rounds", "initial")
    conn.on("units, images, image_candidates, user_state", rows)
    search = AsyncMock(return_value=[])
    task = task_row(plan=json.dumps(BATCHED), phase_cursor=json.dumps({"look_ups": fill_mod.ROUND_LOOK_UPS - 3}))
    out = await fill_mod.fill(task, _deps(search=search), _guard())
    assert search.await_count == 3 and out.cursor["look_ups"] == fill_mod.ROUND_LOOK_UPS
    search.reset_mock()
    out = await fill_mod.fill({**task, "phase_cursor": json.dumps(out.cursor)}, _deps(search=search), _guard())
    assert not search.await_count


@pytest.mark.asyncio
async def test_fill_releases_when_a_batch_is_ready_and_leaves_old_tasks_alone(conn):
    out = await fill_mod.fill(task_row(), _deps(), _guard())  # planned before batches
    assert out.phase == phases.SUMMARIZE and not conn.calls
    conn.on("SELECT kind FROM mw_agent_task_rounds", "more")
    rows = [ready() for _ in range(12)]
    conn.on("units, images, image_candidates, user_state", rows)
    search = AsyncMock(side_effect=RuntimeError("Brave down"))
    out = await fill_mod.fill(task_row(plan=json.dumps(BATCHED)), _deps(search=search), _guard())
    assert out.phase == phases.SUMMARIZE and not search.await_count
    conn.on("units, images, image_candidates, user_state", rows[:3])
    out = await fill_mod.fill(task_row(plan=json.dumps(BATCHED)), _deps(search=search), _guard())
    assert out.phase == phases.PROVIDERS and out.cursor["searched"] is True


@pytest.mark.asyncio
async def test_a_failed_look_up_or_photo_never_fails_the_step():
    deps = _deps(search=AsyncMock(side_effect=RuntimeError("out")))
    assert await fill_mod._look_up(item_row(), item_kind="listing", where="", deps=deps) is None
    row = item_row(images="[]", image_candidates=json.dumps([{"source_url": "https://x.test/a.jpg"}]))
    assert await fill_mod._photos([row], _deps(rehost=AsyncMock(side_effect=RuntimeError("cdn"))), "p") == {}


# ── Sonnet, only when Haiku's answer fails ───────────────────────────────────

@pytest.fixture
def two_models(monkeypatch):
    monkeypatch.setattr(model_run.models, "offered", lambda: (CLAUDE_HAIKU, CLAUDE_SONNET))
    seen = []

    async def phase(owner, **kwargs):
        seen.append(owner.model)
        if owner.model == CLAUDE_HAIKU:
            raise runner.AgentRunError("broken json")
        return SimpleNamespace(result={"ok": owner.model})

    monkeypatch.setattr(model_run.phase_run, "run_model_phase", phase)
    return seen


@pytest.mark.asyncio
async def test_haiku_hands_a_failed_phase_to_sonnet_once_then_takes_it_back(conn, monkeypatch, two_models):
    monkeypatch.delenv(model_run.SONNET_ENV, raising=False)
    task = task_row(model=CLAUDE_HAIKU)
    out = await model_run.run_model_phase(task, phase="summarize", escalate=True)
    assert out.result == {"ok": CLAUDE_SONNET} and two_models == [CLAUDE_HAIKU, CLAUDE_SONNET]
    assert not conn.ran("SET model") and task["model"] == CLAUDE_HAIKU  # the next phase is Haiku's again
    with pytest.raises(runner.AgentRunError):
        await model_run.run_model_phase(task, phase="discover")  # not asked to escalate
    assert two_models[-1] == CLAUDE_HAIKU
    monkeypatch.setenv(model_run.SONNET_ENV, "off")
    assert await model_run.escalation_model(task) is None
    monkeypatch.setenv(model_run.SONNET_ENV, "on")
    assert await model_run.escalation_model(task) == CLAUDE_SONNET
    assert await model_run.escalation_model(task_row(model=CLAUDE_SONNET)) is None  # already the stronger one
    monkeypatch.setattr(model_run.models, "offered", lambda: (CLAUDE_HAIKU,))
    assert await model_run.escalation_model(task) is None


# ── the suggestion ───────────────────────────────────────────────────────────

def test_nearby_places_to_widen_to():
    assert suggest.nearby("San Francisco, CA") == ["Oakland", "Richmond"]
    assert suggest.nearby("New York, NY") == ["Jersey City", "Newark"]
    assert suggest.nearby(None) == [] and suggest.nearby("Atlantis Under The Sea") == []


def test_a_thin_batch_suggests_looking_wider():
    got = suggest.diagnose(plan=BATCHED, shown=3, ready_waiting=0, short={"price": 12, "photo": 4},
                           hidden_by={"price": 6, "pets": 2}, hidden_prices=[3640.0, 3900.0, 2000.0],
                           waiting_prices=[], room=40, near=["Oakland", "Richmond"])
    assert got["kind"] == "thin"
    assert [o["label"] for o in got["options"]] == ["Also search Oakland and Richmond",
                                                    "Raise the limit to $3,700 a month", "Keep looking"]
    assert [o["round"] for o in got["options"]] == ["refine", "refine", "more"]
    assert "Of the others, 12 have no price and 4 have no photo." in got["text"]
    assert "6 were left out for price" in got["text"]
    assert got["text"].endswith("Want me to also search Oakland and Richmond?")
    over = suggest.diagnose(plan=BATCHED, shown=2, ready_waiting=0, short={batches.OVER_LIMIT: 5, "photo": 1},
                            hidden_by={"pets": 2}, hidden_prices=[], waiting_prices=[], room=0,
                            over_prices=[3610.0, 4200.0, 3900.0, 3750.0, 4400.0], near=[])
    assert "Of the others, 5 are listed over your limit and 1 has no photo." in over["text"]
    # Other sites' prices count toward the limit to raise, and say how far.
    assert over["options"] == [{"label": "Raise the limit to $3,700 a month", "round": "refine",
                                "directive": "Raise the price limit to $3,700 a month"}]
    none = suggest.diagnose(plan=BATCHED, shown=0, ready_waiting=0, short={}, hidden_by={"pets": 2},
                            hidden_prices=[], waiting_prices=[], room=0, near=[])
    assert none["options"] == [{"label": "Drop \"Pets includes Dogs OK\"", "round": "refine",
                                "directive": "Pets: drop that requirement"}]
    assert none["text"].startswith("I couldn't find any")
    assert suggest.diagnose(plan=BATCHED, shown=0, ready_waiting=0, short={}, hidden_by={},
                            hidden_prices=[], waiting_prices=[], room=0, near=[]) is None


def test_a_broad_search_suggests_narrowing_it():
    plan = {**BATCHED, "constraints": [], "item_kind": "listing"}
    got = suggest.diagnose(plan=plan, shown=10, ready_waiting=40, short={}, hidden_by={}, hidden_prices=[],
                           waiting_prices=[2100.0, 2600.0, 3050.0, 3300.0, 4000.0], room=10, near=[])
    assert got["kind"] == "broad" and got["options"][0]["label"] == "Only under $3,100"
    assert got["text"] == "There are 40 more like these. Want to narrow it down, say only under $3,100?"
    assert suggest.diagnose(plan=BATCHED, shown=10, ready_waiting=5, short={}, hidden_by={}, hidden_prices=[],
                            waiting_prices=[], room=10, near=[]) is None
    assert suggest.view(None, "x") is None
    assert suggest.view(got, "  Lots of these!  ")["text"] == "Lots of these!"
    assert suggest.view(got, None)["text"] == got["text"]


def test_the_models_question_states_only_numbers_it_was_given():
    batch = {"F1": "item-1"}
    args = {"headline": "Found one", "summary": "One fits.", "sections": [], "top": [{"id": "F1", "why": "ok"}],
            "question": "I'm having a hard time. Raise it to $3,700?"}
    out, _ = contracts.normalize_summary(args, batch=batch, item_texts={"item-1": "x"}, citable=set(),
                                         context="Raise the limit to $3,700 a month")
    assert out["question"] == "I'm having a hard time. Raise it to $3,700?"
    out, warnings = contracts.normalize_summary({**args, "question": "Raise it to $9,999?"}, batch=batch,
                                                item_texts={"item-1": "x"}, citable=set(), context="")
    assert "question" not in out and any("question" in w for w in warnings)


@pytest.mark.asyncio
async def test_summarize_releases_the_next_ten_and_asks_when_thin(conn, monkeypatch):
    shown_before, now, unready = ready(), ready(), item_row(id=uuid4(), fields="{}", images="[]")
    pricey = ready(fields=json.dumps({"price": _claimed(3520), "phone": PHONE}))
    conn.on("SELECT kind FROM mw_agent_task_rounds", "more")
    conn.on("SELECT summary FROM mw_agent_task_rounds",
            [{"summary": json.dumps({"batch": [str(shown_before["id"])], "looked_up": []})}])
    conn.on("units, images, image_candidates, user_state", [shown_before, pricey, now, unready])
    conn.on("jsonb_array_elements(CASE WHEN", [{"field": "price", "n": 2}])
    conn.on("AS price FROM mw_agent_task_items", [{"price": 3640.0}])
    monkeypatch.setattr(suggest, "nearby", lambda _location, n=2: ["Oakland", "Richmond"])
    seen = []

    async def run(task, **kwargs):
        seen.append(kwargs)
        state = RunState(started=time.monotonic())
        out, _ = kwargs["contract"].normalize({
            "headline": "One more", "summary": "One fits.", "sections": [], "top": [{"id": "F1", "why": "ok"}],
            "question": "I'm having a hard time finding more. Want me to also search Oakland and Richmond?",
        }, state)
        return SimpleNamespace(result=out)

    monkeypatch.setattr(model_run, "run_model_phase", run)
    task = task_row(plan=json.dumps(BATCHED), phase_cursor=json.dumps({"looked_up": ["a"]}))
    out = await M.summarize(task, _deps(), _guard())
    assert out.status == "done" and seen[0]["escalate"] is True
    assert "Suggestion (thin)" in seen[0]["user_text"]
    [save] = conn.ran("UPDATE mw_agent_task_rounds SET summary")
    summary = json.loads(save[2][3])
    assert summary["batch"] == [str(now["id"])] and summary["looked_up"] == ["a"]
    assert summary["counts"]["shown"] == 2 and summary["counts"]["waiting"] == 2
    # $3,520 at another site: waits, and is the figure the limit would have to reach.
    assert "Raise the limit to $3,600 a month" in [o["label"] for o in summary["question"]["options"]]
    assert summary["question"]["text"].startswith("I'm having a hard time")
    assert summary["question"]["options"][0]["label"] == "Also search Oakland and Richmond"
    assert summary["top"][0]["item_id"] == str(now["id"])
