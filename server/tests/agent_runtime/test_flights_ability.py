"""Flights as a registry ability: the assistant gets `search_flights` and a
`flights` result block rebuilt from what the run's own searches returned."""
import pytest

from app.matcha.services.matcha_work.agent_runtime import catalog, result, runner
from app.matcha.services.matcha_work.agent_runtime.abilities import flights as flights_ability
from app.matcha.services.matcha_work.agent_card import flights

from tests.agent_card.test_flights import ROUND_TRIP, FakeDuffel, _simple_offers

from .helpers import FakeClient, call, context, response, wire_store

COMBO = "combo:ow_SFOJFK_2026-11-12+ow_JFKSFO_2026-11-15"


def _ability(duffel, **over):
    return flights_ability.build(token=lambda: "duffel_test_abc", session=lambda _t: duffel.session(), **over)


async def _run(client, abilities, **ctx_over):
    return await runner.run_agent(
        context(**ctx_over), client=client, abilities=abilities,
        contract=runner.ResultContract(
            finish=result.finish_tool(abilities),
            normalize=lambda args, state: result.normalize(args, state, abilities),
        ),
        instructions="sys", first_input=[],
    )


@pytest.mark.asyncio
async def test_the_flights_block_is_rebuilt_from_the_search_not_the_model(monkeypatch):
    record, _claim, _resolve = wire_store(monkeypatch)
    duffel = FakeDuffel(_simple_offers)
    client = FakeClient([
        response(call("search_flights", ROUND_TRIP)),
        response(call("finish", {
            "headline": "Two one-ways are cheapest", "summary": "Saves $110.",
            "blocks": [{"type": "flights", "query_summary": "SFO–JFK", "options": [
                {"offer_id": COMBO, "label": "Cheapest", "total_amount": "1.00"},
                {"offer_id": "off_invented", "label": "Fastest"},
            ]}],
        })),
    ])
    out = await _run(client, [_ability(duffel)])
    [block] = out.result["blocks"]
    assert block["type"] == "flights"
    options = block["flights"]["options"]
    assert [o["id"] for o in options] == [COMBO]
    assert options[0]["total_amount"] == "310.00"  # the model's "1.00" is ignored
    assert block["flights"]["test_data"] is True
    assert block["flights"]["privacy"] == flights.privacy_disclosure()
    assert any("off_invented" in w for w in out.warnings)
    # The search is audited as a search step, with the offer count, not the fares.
    step = next(c.args for c in record.await_args_list if c.args[2] == "search_flights")
    assert step[3] == "search" and step[6]["options"] >= 1
    tools = [t.get("name") or t.get("type") for t in client.calls[0]["tools"]]
    assert tools == ["search_flights", "finish"]


@pytest.mark.asyncio
async def test_a_flights_block_without_a_search_is_dropped(monkeypatch):
    wire_store(monkeypatch)
    client = FakeClient([response(call("finish", {
        "headline": "h", "summary": "s",
        "blocks": [{"type": "flights", "options": [{"offer_id": COMBO}]}],
    }))])
    out = await _run(client, [_ability(FakeDuffel(_simple_offers))])
    assert out.result["blocks"] == []
    assert any("flights block" in w or "flight option" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_searches_are_capped_and_a_crash_is_a_tool_error(monkeypatch):
    wire_store(monkeypatch)

    class Boom:
        async def search(self, args, *, seconds):
            raise RuntimeError("boom")

    ability = flights_ability.build(token=lambda: "duffel_test_abc", session=lambda _t: Boom(), max_searches=1)
    client = FakeClient([
        response(call("search_flights", ROUND_TRIP), call("search_flights", ROUND_TRIP)),
        response(call("finish", {"headline": "h", "summary": "s"})),
    ])
    await _run(client, [ability])
    outputs = [item["output"] for item in client.calls[1]["input"]]
    assert "The flight search failed: RuntimeError" in outputs[0]
    assert "limit reached" in outputs[1]


def test_the_assistant_offers_flights_only_with_a_token(monkeypatch):
    async def no_fetch(_url):
        return {}, set()

    situation = catalog.Situation(private=False, grants={}, google_connected=False, granted_scopes=frozenset())
    monkeypatch.delenv(flights.TOKEN_ENV, raising=False)
    keys = [a.key for a in catalog.abilities_for(catalog.build_catalog(fetch_page=no_fetch), situation)]
    assert "flights" not in keys
    monkeypatch.setenv(flights.TOKEN_ENV, "duffel_test_abc")
    keys = [a.key for a in catalog.abilities_for(catalog.build_catalog(fetch_page=no_fetch), situation)]
    # Read-only, so a shared project chat gets it too.
    assert keys == ["web", "shopping", "flights"]


def test_the_prompt_says_it_cannot_book():
    block = flights_ability.build(token=lambda: "x").prompt_block(context())
    assert "search_flights" in block and "cannot book" in block and "hidden-city" in block


@pytest.mark.asyncio
async def test_the_chat_card_gets_the_compact_flight_rows(monkeypatch):
    from app.matcha.services.matcha_work.agent_card import chat_flow

    wire_store(monkeypatch)
    duffel = FakeDuffel(_simple_offers)
    client = FakeClient([
        response(call("search_flights", ROUND_TRIP)),
        response(call("finish", {"headline": "h", "summary": "s", "blocks": [
            {"type": "flights", "options": [{"offer_id": COMBO, "label": "Cheapest"}]}]})),
    ])
    out = await _run(client, [_ability(duffel)])
    [block] = result.chat_view(out.result)["blocks"]
    assert block == {"type": "flights", "flights": chat_flow.flights_view(out.result["blocks"][0]["flights"])}
    assert block["flights"]["options"][0]["price_text"] and block["flights"]["test_data"] is True
    # A block with nothing left to show is dropped from the card.
    assert result.chat_view({"blocks": [{"type": "flights", "flights": {"options": []}}]})["blocks"] == []
