"""find_places and the places block: Google Maps listings as the run found them. No network."""
from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work.agent_runtime import catalog, result
from app.matcha.services.matcha_work.agent_runtime.abilities import places, sales
from app.matcha.services.matcha_work.agent_runtime.context import RunLimits, RunState
from app.matcha.services.matcha_work.search_apis import ProviderError

from .helpers import context


@dataclass
class Item:
    title: str
    url: str | None
    provider_id: str | None = None
    subtitle: str = ""
    fields: dict = field(default_factory=dict)
    point: tuple | None = None


def item(n, *, site=True, **values):
    base = {"address": f"{n} Sunset Blvd, Los Angeles, CA", "phone": f"(213) 555-{n:04d}", "rating": 4.5,
            "review_count": 100 + n, "cuisine": "Coffee shop", "price_level": "$$"}
    base.update(values)
    url = f"https://cafe{n}.test/" if site else f"https://www.google.com/maps/search/?api=1&query=x&query_place_id=p{n}"
    return Item(title=f"Cafe {n}", url=url, provider_id=f"p{n}",
                fields={k: {"value": v} for k, v in base.items() if v is not None}, point=(34.0, -118.2))


class Provider:
    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    async def search_pages(self, source, query, *, pages=1, ll=None):
        self.asked.append((source, query, pages))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def state():
    return RunState(started=0.0, sessions={places.KEY: places.PlacesSession()})


async def find(st, provider, monkeypatch, ctx=None, **args):
    monkeypatch.setattr(places, "_provider", lambda: provider)
    return await places.FIND_PLACES.handler(ctx or context(), st, args, 60)


def test_places_needs_a_provider_key_and_nothing_switched_on(monkeypatch):
    ability = places.build()
    assert ability.consent_version is None and not ability.private_only
    monkeypatch.setattr(places, "_provider", lambda: object())
    assert catalog.availability(ability, catalog.Situation(private=False)).available
    monkeypatch.setattr(places, "_provider", lambda: None)
    assert not catalog.availability(ability, catalog.Situation(private=True)).available


@pytest.mark.asyncio
async def test_find_places_keeps_each_place_once_with_its_links_as_provenance(monkeypatch):
    st = state()
    provider = Provider([item(1), item(2, site=False)], [item(2, site=False), item(3)])
    first = await find(st, provider, monkeypatch, query="coffee shops in Silver Lake, Los Angeles", pages=3)
    assert provider.asked == [("places", "coffee shops in Silver Lake, Los Angeles", 3)]
    assert first.payload["new_places"] == 2 and first.payload["places"][0].startswith("P1 | Cafe 1 | Coffee shop | 4.5★")
    assert first.payload["places"][0].split(" | ")[-2:] == ["(213) 555-0001", "https://cafe1.test/"]
    assert first.payload["places"][1].split(" | ")[-1] == "no website"
    assert first.provenance >= {"https://cafe1.test/"} and any("query_place_id=p2" in u for u in first.provenance)
    second = await find(st, provider, monkeypatch, query="coffee shops in Echo Park, Los Angeles")
    assert second.payload["new_places"] == 1 and second.payload["already_found"] == 1
    assert second.payload["places"][0].startswith("P3 | Cafe 3")
    assert st.sessions[places.KEY].paid == 4


@pytest.mark.asyncio
async def test_find_places_holds_to_its_paid_page_budget(monkeypatch):
    st = state()
    st.sessions[places.KEY].paid = places.MAX_PAID - 1
    provider = Provider([item(1)])
    out = await find(st, provider, monkeypatch, query="gyms in Austin", pages=3)
    assert provider.asked[0][2] == 1, "only what is left of the budget is asked for"
    spent = await find(st, provider, monkeypatch, query="gyms in Dallas")
    assert "budget used up" in spent.payload["error"] and len(provider.asked) == 1
    assert out.payload["new_places"] == 1


@pytest.mark.asyncio
async def test_a_provider_error_is_a_tool_error_the_model_can_route_around(monkeypatch):
    out = await find(state(), Provider(ProviderError("Google Places answered 500")), monkeypatch, query="x in y")
    assert "web_search" in out.payload["error"] and out.status == "error"


@pytest.mark.asyncio
async def test_a_long_list_reaches_the_model_inside_the_output_budget(monkeypatch):
    st = state()
    ctx = context(limits=RunLimits(max_tool_output_chars=4000))
    out = await find(st, Provider([item(n) for n in range(1, 61)]), monkeypatch, ctx=ctx, query="cafes in LA", pages=3)
    shown = out.payload["places"]
    assert places.MIN_ROWS <= len(shown) < 60 and "not_shown_here" in out.payload
    assert len(st.sessions[places.KEY].places) == 60, "every place is kept for the block"


@pytest.mark.asyncio
async def test_the_block_is_rebuilt_from_what_the_run_found(monkeypatch):
    st = state()
    await find(st, Provider([item(1), item(2), item(3)]), monkeypatch, query="cafes in LA")
    everything, _ = places.gate_block("places", {"title": "LA cafes", "place_ids": []}, st)
    assert [p["id"] for p in everything["places"]] == ["P1", "P2", "P3"] and everything["title"] == "LA cafes"
    assert everything["places"][0]["phone"] == "(213) 555-0001" and everything["places"][0]["website"] == "https://cafe1.test/"
    picked, warnings = places.gate_block("places", {"place_ids": ["p3", "P1", "P9"]}, st)
    assert [p["id"] for p in picked["places"]] == ["P3", "P1"] and warnings == ["Dropped 1 place id(s) this run did not find"]
    assert places.gate_block("places", {}, state())[0] is None


@pytest.mark.asyncio
async def test_a_list_can_leave_a_few_out_instead_of_naming_every_place_kept(monkeypatch):
    st = state()
    await find(st, Provider([item(n) for n in range(1, 6)]), monkeypatch, query="cafes in LA")
    block, warnings = places.gate_block("places", {"place_ids": [], "leave_out_ids": ["p2", "P4"]}, st)
    assert [p["id"] for p in block["places"]] == ["P1", "P3", "P5"] and block["found"] == 5 and not warnings
    assert places.chosen_ids(st.sessions[places.KEY].places, ["P5", "P1"], ["P1"]) == (["P5"], 0)
    assert places.MAX_BLOCK >= places.MAX_PAID * 20, "a list holds everything a run can find"


@pytest.mark.asyncio
async def test_a_list_left_out_of_the_answer_is_added(monkeypatch):
    st = state()
    await find(st, Provider([item(1), item(2), item(3)]), monkeypatch, query="cafes in LA", pages=3)
    ability = places.build()
    out, _ = result.normalize({"headline": "Found 3 cafes", "summary": "Three cafes."}, st, [ability])
    assert [b["type"] for b in out["blocks"]] == ["places"] and len(out["blocks"][0]["places"]) == 3
    two = state()
    await find(two, Provider([item(1), item(2)], [item(3)]), monkeypatch, query="cafes in Silver Lake")
    await find(two, Provider([item(3)]), monkeypatch, query="cafes in Echo Park")
    out, _ = result.normalize({"headline": "Cafes", "summary": "Three cafes."}, two, [ability])
    assert len(out["blocks"][0]["places"]) == 3, "two searches build a list too"


@pytest.mark.asyncio
async def test_a_place_looked_up_is_not_turned_into_a_list(monkeypatch):
    # "What's Cafe 1's number?" finds the cafe and its neighbours on one page;
    # an answer that leaves them out meant to.
    lookup = state()
    await find(lookup, Provider([item(n) for n in range(1, 6)]), monkeypatch, query="Cafe 1 Los Angeles")
    out, _ = result.normalize({"headline": "Cafe 1", "summary": "(213) 555-0001."}, lookup, [places.build()])
    assert out["blocks"] == []
    picked, _ = places.gate_block("places", {"place_ids": ["P1"]}, lookup)
    assert [p["id"] for p in picked["places"]] == ["P1"], "it can still show the one it means"


@pytest.mark.asyncio
async def test_sales_saves_found_places_by_id_with_their_sources(monkeypatch):
    st = state()
    st.sessions[sales.KEY] = sales.SalesSession(campaigns={"c1"})
    await find(st, Provider([item(1), item(2, site=False)]), monkeypatch, query="cafes in LA")
    imported = AsyncMock(return_value={"added": 2, "duplicates": 0, "suppressed": 0})
    monkeypatch.setattr(sales.store, "import_prospects", imported)
    tool = next(t for t in sales.build().tools if t.name == "add_places_to_campaign")
    out = await tool.handler(context(), st, {"campaign_id": "00000000-0000-0000-0000-000000000001",
                                             "place_ids": []}, 60)
    assert "error" in out.payload, "the campaign must be one this run read"
    st.sessions[sales.KEY].campaigns.add("00000000-0000-0000-0000-000000000001")
    out = await tool.handler(context(), st, {"campaign_id": "00000000-0000-0000-0000-000000000001",
                                             "place_ids": []}, 60)
    assert out.payload == {"added": 2, "duplicates": 0, "suppressed": 0}
    prospects = imported.await_args.args[2].prospects
    assert prospects[0].company == "Cafe 1" and prospects[0].website == "https://cafe1.test/"
    assert "Phone: (213) 555-0001" in prospects[0].notes and prospects[0].email == ""
    assert prospects[0].sources[0] == "https://cafe1.test/" and "query_place_id=p1" in prospects[0].sources[1]
    assert prospects[1].website == "" and len(prospects[1].sources) == 1


@pytest.mark.asyncio
async def test_sales_refuses_places_this_run_did_not_find(monkeypatch):
    st = state()
    st.sessions[sales.KEY] = sales.SalesSession(campaigns={"00000000-0000-0000-0000-000000000001"})
    tool = next(t for t in sales.build().tools if t.name == "add_places_to_campaign")
    out = await tool.handler(context(), st, {"campaign_id": "00000000-0000-0000-0000-000000000001",
                                             "place_ids": ["P1"]}, 60)
    assert "find_places" in out.payload["error"]


@pytest.mark.asyncio
async def test_sales_saves_at_most_fifty_places_a_call(monkeypatch):
    st = state()
    campaign = "00000000-0000-0000-0000-000000000001"
    st.sessions[sales.KEY] = sales.SalesSession(campaigns={campaign})
    await find(st, Provider([item(n) for n in range(1, 61)]), monkeypatch, query="cafes in LA", pages=3)
    imported = AsyncMock(return_value={"added": 50, "duplicates": 0, "suppressed": 0})
    monkeypatch.setattr(sales.store, "import_prospects", imported)
    tool = next(t for t in sales.build().tools if t.name == "add_places_to_campaign")
    out = await tool.handler(context(), st, {"campaign_id": campaign, "place_ids": []}, 60)
    assert "60 places" in out.payload["error"] and "50" in out.payload["error"] and not imported.await_count
    out = await tool.handler(context(), st, {"campaign_id": campaign, "place_ids": [],
                                             "leave_out_ids": [f"P{n}" for n in range(51, 61)]}, 60)
    assert out.payload["added"] == 50 and len(imported.await_args.args[2].prospects) == 50
    assert tool.parameters["properties"]["place_ids"]["maxItems"] == sales.MAX_PROSPECTS_PER_CALL == 50
