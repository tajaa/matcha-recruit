import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest

from app.matcha.services.matcha_work.agent_card import agent, chat_flow, flights, schema, tools
from app.matcha.services.matcha_work.agent_card.prompt import build_system_prompt

from .test_agent import _call, _FakeClient, _kwargs, _response

TODAY = date(2026, 10, 1)


def _seg(sid, origin, dest, dep, arr, code="UA", number="100", checked=0, carry=1, duration="PT5H30M"):
    return {
        "id": sid,
        "origin": {"iata_code": origin},
        "destination": {"iata_code": dest},
        "departing_at": dep,
        "arriving_at": arr,
        "duration": duration,
        "marketing_carrier": {"name": {"UA": "United", "DL": "Delta", "ZZ": "Duffel Airways"}.get(code, code),
                              "iata_code": code},
        "marketing_carrier_flight_number": number,
        "passengers": [{"passenger_id": "pas_1", "baggages": [
            {"type": "checked", "quantity": checked}, {"type": "carry_on", "quantity": carry},
        ]}],
    }


def _offer(oid, amount, *slices, currency="USD", brand=None, changeable=True):
    return {
        "id": oid,
        "total_amount": amount,
        "total_currency": currency,
        "owner": {"name": "United", "iata_code": "UA"},
        "expires_at": "2026-10-01T12:30:00Z",
        "conditions": {
            "change_before_departure": {"allowed": changeable},
            "refund_before_departure": {"allowed": False},
        },
        "passengers": [{"id": "pas_1", "type": "adult"}],
        "slices": [
            {"segments": segs, "duration": "PT5H30M", "fare_brand_name": brand} for segs in slices
        ],
    }


def _nonstop(prefix, origin, dest, day, number="100", checked=0, code="UA"):
    return [_seg(f"{prefix}_seg", origin, dest, f"{day}T07:05:00", f"{day}T15:40:00",
                 code=code, number=number, checked=checked)]


class FakeDuffel:
    """Answers offer requests from a function of the requested slices."""

    def __init__(self, offers_for, *, offers_by_id=None, places=None, fail=()):
        self.offers_for = offers_for
        self.offers_by_id = offers_by_id or {}
        self.places = places or {}
        self.fail = set(fail)
        self.requests: list[dict] = []
        self.offer_reads: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Duffel-Version"] == "v2"
        assert request.headers["Authorization"].startswith("Bearer duffel_test_")
        if request.url.path == "/air/offer_requests":
            body = json.loads(request.content)["data"]
            self.requests.append(body)
            key = tuple((s["origin"], s["destination"], s["departure_date"]) for s in body["slices"])
            if key in self.fail:
                return httpx.Response(422, json={"errors": [{"message": "No such route"}]})
            return httpx.Response(200, json={"data": {"offers": self.offers_for(key)}})
        if request.url.path.startswith("/air/offers/"):
            oid = request.url.path.rsplit("/", 1)[-1]
            self.offer_reads.append(oid)
            assert request.url.params["return_available_services"] == "true"
            return httpx.Response(200, json={"data": self.offers_by_id[oid]})
        if request.url.path == "/places/suggestions":
            key = request.url.params.get("query") or "near:" + request.url.params["lat"]
            return httpx.Response(200, json={"data": self.places.get(key, [])})
        raise AssertionError(request.url)

    def session(self):
        return flights.FlightSession(
            "duffel_test_abc", transport=httpx.MockTransport(self.handler), today=TODAY,
        )


ROUND_TRIP = {"origin": "SFO", "destination": "JFK", "depart_date": "2026-11-12", "return_date": "2026-11-15"}


def _simple_offers(key):
    """A round-trip offer for the exact trip, one-way legs, nothing else."""
    if len(key) == 2:
        (o, d, day), (_, _, back) = key
        return [_offer(f"rt_{o}{d}_{day}_{back}", "420.00", _nonstop("a", o, d, day), _nonstop("b", d, o, back, "200"))]
    (o, d, day), = key
    price = "150.00" if o == "SFO" else "160.00"
    return [_offer(f"ow_{o}{d}_{day}", price, _nonstop("c", o, d, day, "300" if o == "SFO" else "301", code="DL"))]


# ── query validation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("args, error", [
    ({**ROUND_TRIP, "origin": "SF"}, "IATA"),
    ({**ROUND_TRIP, "destination": "SFO"}, "same"),
    ({**ROUND_TRIP, "depart_date": "2026-09-01"}, "past"),
    ({**ROUND_TRIP, "return_date": "2026-11-01"}, "before"),
    ({**ROUND_TRIP, "depart_date": "2027-12-01", "return_date": None}, "days ahead"),
    ({**ROUND_TRIP, "depart_date": "next tuesday"}, "date like"),
    ({**ROUND_TRIP, "adults": 4, "children": 3}, "at most 6"),
    ({**ROUND_TRIP, "infants": 2}, "infants"),
    ({**ROUND_TRIP, "cabin": "luxury"}, "cabin"),
    ({**ROUND_TRIP, "flexible_days": 5}, "flexible_days"),
    ({**ROUND_TRIP, "adults": 1.5}, "whole number"),
])
def test_bad_queries_are_refused_with_a_reason(args, error):
    with pytest.raises(flights.FlightError, match=error):
        flights.parse_query(args, today=TODAY)


def test_query_defaults_and_passengers():
    q = flights.parse_query({**ROUND_TRIP, "origin": "sfo", "children": 1, "infants": 1, "checked_bags": 1},
                            today=TODAY)
    assert q.origin == "SFO" and q.round_trip and q.cabin == "economy" and q.max_connections == 1
    assert q.passengers() == [{"type": "adult"}, {"age": 8}, {"age": 1}]
    assert "SFO → JFK, Nov 12 – Nov 15" in q.summary() and "1 checked bag each" in q.summary()


# ── the search plan ───────────────────────────────────────────────────────────

def test_plan_puts_the_exact_trip_and_one_way_legs_first_then_dates_then_airports():
    q = flights.parse_query({**ROUND_TRIP, "flexible_days": 1}, today=TODAY)
    plan = flights.plan_variants(q, origins=["SFO", "OAK"], destinations=["JFK", "EWR"], budget=99, today=TODAY)
    assert plan[0].slices == (("SFO", "JFK", date(2026, 11, 12)), ("JFK", "SFO", date(2026, 11, 15)))
    assert [v.leg for v in plan[1:3]] == ["out", "back"]
    # 8 date shifts (3x3 minus the exact), nearest first, then 3 other airport pairs.
    shifts = [v.date_shift for v in plan[3:11]]
    assert set(shifts[:4]) == {(-1, 0), (1, 0), (0, -1), (0, 1)}  # one day off, before two
    assert all(not v.airports_changed for v in plan[:11])
    assert [(v.slices[0][0], v.slices[0][1]) for v in plan[11:]] == [("SFO", "EWR"), ("OAK", "JFK"), ("OAK", "EWR")]
    assert len(flights.plan_variants(q, origins=["SFO"], destinations=["JFK"], budget=4, today=TODAY)) == 4


def test_plan_skips_dates_in_the_past_and_returns_before_departure():
    q = flights.parse_query({"origin": "SFO", "destination": "JFK", "depart_date": "2026-10-01",
                             "return_date": "2026-10-02", "flexible_days": 1}, today=TODAY)
    plan = flights.plan_variants(q, origins=["SFO"], destinations=["JFK"], budget=99, today=TODAY)
    for v in plan:
        dates = [s[2] for s in v.slices]
        assert dates[0] >= TODAY and dates == sorted(dates)


# ── searching ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_round_trip_is_also_priced_as_two_one_way_tickets():
    duffel = FakeDuffel(_simple_offers)
    session = duffel.session()
    out = await session.search(ROUND_TRIP)
    assert out["offer_requests"] == 3 and out["failed_requests"] == 0
    ids = [o["offer_id"] for o in out["options"]]
    combo = "combo:ow_SFOJFK_2026-11-12+ow_JFKSFO_2026-11-15"
    assert ids[0] == combo  # 150 + 160 = 310 < 420
    first = session.option(combo)
    assert first["ticketing"] == "separate" and first["total_amount"] == "310.00"
    assert flights.SEPARATE_TICKETS_WARNING in first["warnings"]
    assert session.option("rt_SFOJFK_2026-11-12_2026-11-15")["ticketing"] == "single"
    # Only the itinerary is sent: no names, no ages beyond the pricing bands.
    assert duffel.requests[0]["passengers"] == [{"type": "adult"}]
    assert set(duffel.requests[0]) == {"slices", "passengers", "cabin_class", "max_connections"}


@pytest.mark.asyncio
async def test_the_offer_request_budget_is_shared_across_calls():
    duffel = FakeDuffel(_simple_offers)
    session = duffel.session()
    await session.search({**ROUND_TRIP, "flexible_days": 2})  # wants 3 + 24 requests
    assert len(duffel.requests) == flights.MAX_OFFER_REQUESTS
    again = await session.search(ROUND_TRIP)
    assert "budget used up" in again["error"]
    assert len(duffel.requests) == flights.MAX_OFFER_REQUESTS


@pytest.mark.asyncio
async def test_partial_failures_are_reported_and_total_failure_is_an_error():
    exact = (("SFO", "JFK", "2026-11-12"),)
    duffel = FakeDuffel(_simple_offers, fail={exact})
    out = await duffel.session().search({**ROUND_TRIP, "return_date": None, "flexible_days": 1})
    assert out["failed_requests"] == 1 and out["options"]
    failing = FakeDuffel(_simple_offers, fail={exact})
    out = await failing.session().search({**ROUND_TRIP, "return_date": None})
    assert "failed" in out["error"]


@pytest.mark.asyncio
async def test_bad_args_come_back_as_a_tool_error():
    out = await FakeDuffel(_simple_offers).session().search({"origin": "SFO"})
    assert "IATA" in out["error"]


@pytest.mark.asyncio
async def test_nearby_airports_come_from_places():
    places = {
        "SFO": [{"type": "airport", "iata_code": "SFO", "latitude": 37.6, "longitude": -122.4}],
        "near:37.6": [
            {"type": "airport", "iata_code": "SFO"},
            {"type": "airport", "iata_code": "OAK"},
            {"type": "city", "iata_code": "SJC", "airports": [{"iata_code": "SJC"}]},
            {"type": "airport", "iata_code": "STS"},
        ],
    }
    duffel = FakeDuffel(_simple_offers, places=places)
    await duffel.session().search({**ROUND_TRIP, "return_date": None, "nearby_airports": True})
    origins = [r["slices"][0]["origin"] for r in duffel.requests]
    assert origins == ["SFO", "OAK", "SJC"]  # at most 2 nearby; JFK had no place data


@pytest.mark.asyncio
async def test_true_total_prices_the_bags_asked_for():
    offers = {
        "cheap": _offer("cheap", "100.00", _nonstop("a", "SFO", "JFK", "2026-11-12")),  # no checked bag
        "bagged": _offer("bagged", "130.00", _nonstop("b", "SFO", "JFK", "2026-11-12", "200", checked=1)),
    }
    offers["cheap"]["available_services"] = [
        {"type": "baggage", "total_amount": "45.00", "total_currency": "USD", "maximum_quantity": 2,
         "passenger_ids": ["pas_1"], "segment_ids": ["a_seg"], "metadata": {"type": "checked"}},
    ]
    duffel = FakeDuffel(lambda key: list(offers.values()), offers_by_id=offers)
    session = duffel.session()
    out = await session.search({**ROUND_TRIP, "return_date": None, "checked_bags": 1})
    assert [o["offer_id"] for o in out["options"]] == ["bagged", "cheap"]  # 130 beats 100 + 45
    assert session.option("cheap")["true_total_amount"] == "145.00"
    assert session.option("bagged")["true_total_amount"] == "130.00"
    assert session.option("bagged")["bag_note"] == "Bags you need are included"
    assert duffel.offer_reads == ["cheap"]


def test_bag_cost_needs_every_slice_covered():
    offer = _offer("x", "100.00", _nonstop("a", "SFO", "JFK", "2026-11-12"), _nonstop("b", "JFK", "SFO", "2026-11-15"))
    per_slice = {"type": "baggage", "total_currency": "USD", "maximum_quantity": 1, "passenger_ids": ["pas_1"]}
    offer["available_services"] = [{**per_slice, "total_amount": "30", "segment_ids": ["a_seg"]}]
    assert flights.bag_cost(offer, bag_type="checked", quantity=1) is None  # return leg unpriced
    offer["available_services"].append({**per_slice, "total_amount": "35", "segment_ids": ["b_seg"]})
    assert flights.bag_cost(offer, bag_type="checked", quantity=1) == Decimal("65")
    offer["available_services"].append({**per_slice, "total_amount": "50", "segment_ids": ["a_seg", "b_seg"]})
    assert flights.bag_cost(offer, bag_type="checked", quantity=1) == Decimal("50")  # whole-trip bag is cheaper
    assert flights.bag_cost(offer, bag_type="checked", quantity=2) is None  # maximum_quantity 1
    assert flights.bag_cost(offer, bag_type="checked", quantity=0) == Decimal(0)


def test_combos_never_mix_currencies():
    v = flights.Variant((("SFO", "JFK", date(2026, 11, 12)),), (0,), False, leg="out")
    out = flights.offer_option(_offer("a", "100", _nonstop("a", "SFO", "JFK", "2026-11-12")), v)
    back = flights.offer_option(_offer("b", "90", _nonstop("b", "JFK", "SFO", "2026-11-15"), currency="EUR"), v)
    assert flights.combine(out, back) is None


def test_malformed_offers_are_skipped():
    v = flights.Variant((("SFO", "JFK", date(2026, 11, 12)),), (0,), False)
    assert flights.offer_option({"id": "x"}, v) is None
    assert flights.offer_option({**_offer("y", "nope", _nonstop("a", "SFO", "JFK", "2026-11-12"))}, v) is None


# ── warnings ──────────────────────────────────────────────────────────────────

def _connecting(first_arrival, second_departure, *, brand=None, changeable=True):
    return _offer("c", "200.00", [
        _seg("s1", "SFO", "DEN", "2026-11-12T06:00:00", first_arrival),
        _seg("s2", "DEN", "JFK", second_departure, "2026-11-13T09:00:00", number="200"),
    ], brand=brand, changeable=changeable)


@pytest.mark.parametrize("arrive, depart, expected", [
    ("2026-11-12T09:00:00", "2026-11-12T09:45:00", "Tight 45 min connection in DEN"),
    ("2026-11-12T22:30:00", "2026-11-13T06:30:00", "Overnight layover in DEN"),
    ("2026-11-12T09:00:00", "2026-11-12T16:00:00", "Long 7h layover in DEN"),
])
def test_layover_warnings(arrive, depart, expected):
    q = flights.parse_query({**ROUND_TRIP, "return_date": None}, today=TODAY)
    v = flights.Variant((("SFO", "JFK", date(2026, 11, 12)),), (0,), False)
    option = flights.offer_option(_connecting(arrive, depart), v)
    assert expected in flights.warnings_for(option, q)


def test_fare_airport_and_date_warnings():
    q = flights.parse_query({**ROUND_TRIP, "return_date": None, "carry_on_bags": 1}, today=TODAY)
    v = flights.Variant((("OAK", "JFK", date(2026, 11, 13)),), (1,), True)
    option = flights.offer_option(
        _offer("b", "90", [_seg("s", "OAK", "JFK", "2026-11-13T07:00:00", "2026-11-13T15:00:00", carry=0)],
               brand="Basic Economy"), v)
    warnings = flights.warnings_for(option, q)
    assert "Basic economy: usually no seat choice and no changes" in warnings
    assert "Carry-on bag not included in the fare" in warnings
    assert "Uses OAK–JFK, not SFO–JFK" in warnings
    assert "Different dates: outbound +1 day" in warnings
    rigid = flights.offer_option(_connecting("2026-11-12T09:00:00", "2026-11-12T11:00:00", changeable=False),
                                 flights.Variant((("SFO", "JFK", date(2026, 11, 12)),), (0,), False))
    assert "This fare can't be changed" in flights.warnings_for(rigid, q)


# ── config, prompt, tools ─────────────────────────────────────────────────────

def test_token_and_travel_detection(monkeypatch):
    monkeypatch.delenv(flights.TOKEN_ENV, raising=False)
    assert flights.enabled() is False
    monkeypatch.setenv(flights.TOKEN_ENV, "  duffel_test_x ")
    assert flights.token() == "duffel_test_x"
    assert flights.is_travel_ask("Find me the cheapest flight SFO to JFK")
    assert flights.is_travel_ask("round-trip to Lisbon in May, nonstop")
    assert not flights.is_travel_ask("Find me the best organic lip balm")
    assert flights.FlightSession("duffel_test_x").test_data
    assert not flights.FlightSession("duffel_live_x").test_data


def test_prompt_and_tools_only_offer_flights_for_travel():
    assert "search_flights" not in build_system_prompt(1)
    assert "search_flights" in build_system_prompt(1, travel=True, flight_search=True)
    assert "hidden-city" in build_system_prompt(1, travel=True, flight_search=True)
    assert "isn't connected" in build_system_prompt(1, travel=True)
    names = [t.get("name") or t["type"] for t in tools.declarations(flights=True)]
    assert names == ["web_search", "search_flights", "fetch_page", "finish"]
    assert [t.get("name") or t["type"] for t in tools.declarations()] == ["web_search", "fetch_page", "finish"]


# ── the result gate ───────────────────────────────────────────────────────────

async def _searched_session():
    session = FakeDuffel(_simple_offers).session()
    await session.search(ROUND_TRIP)
    return session


@pytest.mark.asyncio
async def test_flight_result_is_rebuilt_from_search_data_not_the_model():
    session = await _searched_session()
    combo = "combo:ow_SFOJFK_2026-11-12+ow_JFKSFO_2026-11-15"
    raw = {
        "headline": "Two one-ways save $110", "summary": "Separate tickets are cheapest.",
        "answer_type": "flights", "confidence": "high",
        "top_pick": {"name": "Should be dropped"},
        "flights": {"query_summary": "SFO–JFK", "options": [
            {"offer_id": combo, "label": "Cheapest", "why": ["$110 less"], "total_amount": "1.00"},
            {"offer_id": "off_invented", "label": "Fastest"},
            {"offer_id": combo, "label": "Best value"},
            {"offer_id": "rt_SFOJFK_2026-11-12_2026-11-15", "label": "Luxury"},
        ]},
    }
    result, warnings = schema.normalize_result(raw, set(), flights=session)
    assert result["answer_type"] == "flights" and result["top_pick"] is None
    options = result["flights"]["options"]
    assert [o["id"] for o in options] == [combo, "rt_SFOJFK_2026-11-12_2026-11-15"]
    assert options[0]["total_amount"] == "310.00"  # the model's "1.00" is ignored
    assert options[0]["label"] == "Cheapest" and options[1]["label"] is None
    assert result["flights"]["test_data"] is True
    assert result["flights"]["privacy"] == flights.privacy_disclosure()
    assert result["flights"]["searched_at"]
    assert any("off_invented" in w for w in warnings)
    assert any("Dropped product picks" in w for w in warnings)


@pytest.mark.asyncio
async def test_a_flights_answer_with_no_real_offer_asks_for_a_repair():
    session = await _searched_session()
    raw = {"headline": "h", "summary": "s", "answer_type": "flights", "confidence": "low",
           "flights": {"options": [{"offer_id": "nope"}]}}
    with pytest.raises(ValueError, match="offer_ids"):
        schema.normalize_result(raw, set(), flights=session)
    # Without the flight tool, "flights" falls back to a plain answer.
    result, _ = schema.normalize_result(raw, set())
    assert result["answer_type"] == "answer" and "flights" not in result


# ── the agent loop ────────────────────────────────────────────────────────────

@pytest.fixture
def looped(monkeypatch):
    record_step = AsyncMock()
    monkeypatch.setattr(agent.store, "record_step", record_step)
    monkeypatch.setattr(agent.store, "mark_run", AsyncMock())
    monkeypatch.setattr(agent.board, "set_progress", AsyncMock(return_value=None))
    monkeypatch.setattr(agent.board, "publish_task_updated", AsyncMock())
    monkeypatch.setattr(agent.images, "rehost_images", AsyncMock(return_value=[]))
    monkeypatch.setenv(flights.TOKEN_ENV, "duffel_test_abc")
    duffel = FakeDuffel(_simple_offers)
    real = flights.FlightSession
    monkeypatch.setattr(agent.flights, "FlightSession",
                        lambda token: real(token, transport=httpx.MockTransport(duffel.handler), today=TODAY))
    return record_step, duffel


@pytest.mark.asyncio
async def test_a_travel_card_searches_flights_and_finishes_with_offers(monkeypatch, looped):
    record_step, duffel = looped
    combo = "combo:ow_SFOJFK_2026-11-12+ow_JFKSFO_2026-11-15"
    client = _FakeClient([
        _response(_call("search_flights", ROUND_TRIP)),
        _response(_call("finish", {"result": {
            "headline": "Cheapest: two one-ways", "summary": "Saves $110.", "answer_type": "flights",
            "confidence": "high", "flights": {"options": [{"offer_id": combo, "label": "Cheapest"}]},
        }})),
    ])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    out = await agent.run_card_agent(**_kwargs(ask="Find me the cheapest flight SFO to JFK Nov 12-15"))
    assert out["result"]["flights"]["options"][0]["total_amount"] == "310.00"
    assert [t.get("name") or t["type"] for t in client.calls[0]["tools"]][:2] == ["web_search", "search_flights"]
    assert "search_flights" in client.calls[0]["instructions"]
    steps = [(c.args[2], c.args[3]) for c in record_step.await_args_list]
    assert ("search_flights", "search") in steps  # no new step kind, no migration
    assert len(duffel.requests) == 3


@pytest.mark.asyncio
async def test_flight_searches_are_capped_per_run(monkeypatch, looped):
    monkeypatch.setattr(agent, "_MAX_FLIGHT_SEARCHES", 1)
    client = _FakeClient([
        _response(_call("search_flights", ROUND_TRIP), _call("search_flights", ROUND_TRIP)),
        _response(_call("finish", {"result": {"headline": "h", "summary": "s", "answer_type": "answer",
                                              "confidence": "low"}})),
    ])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    await agent.run_card_agent(**_kwargs(ask="cheapest flight SFO to JFK"))
    second = client.calls[1]["input"][1]
    assert "limit reached" in json.loads(second["output"])["error"]


@pytest.mark.asyncio
async def test_a_crashing_flight_search_is_a_tool_error_not_a_failed_run(monkeypatch, looped):
    boom = Mock()
    boom.search = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(agent.flights, "FlightSession", lambda token: boom)
    client = _FakeClient([
        _response(_call("search_flights", ROUND_TRIP)),
        _response(_call("finish", {"result": {"headline": "h", "summary": "s", "answer_type": "answer",
                                              "confidence": "low"}})),
    ])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    await agent.run_card_agent(**_kwargs(ask="cheapest flight SFO to JFK"))
    assert "RuntimeError" in json.loads(client.calls[1]["input"][0]["output"])["error"]


@pytest.mark.asyncio
async def test_non_travel_cards_and_missing_token_get_no_flight_tool(monkeypatch, looped):
    finish = {"result": {"headline": "h", "summary": "s", "answer_type": "answer", "confidence": "low"}}
    client = _FakeClient([_response(_call("finish", finish))])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    await agent.run_card_agent(**_kwargs())  # lip balm
    assert "search_flights" not in [t.get("name") for t in client.calls[0]["tools"]]
    monkeypatch.delenv(flights.TOKEN_ENV)
    client = _FakeClient([_response(_call("finish", finish))])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    await agent.run_card_agent(**_kwargs(ask="cheapest flight SFO to JFK"))
    assert "search_flights" not in [t.get("name") for t in client.calls[0]["tools"]]
    assert "isn't connected" in client.calls[0]["instructions"]


# ── chat ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_shows_flight_rows_and_never_offers_to_buy():
    session = await _searched_session()
    combo = "combo:ow_SFOJFK_2026-11-12+ow_JFKSFO_2026-11-15"
    result, _ = schema.normalize_result({
        "headline": "Cheapest: two one-ways", "summary": "Saves $110.", "answer_type": "flights",
        "confidence": "high", "flights": {"options": [{"offer_id": combo, "label": "Cheapest"}]},
    }, set(), flights=session)
    assert chat_flow.purchase_offer(result) is None
    view = chat_flow.result_view(result)
    row = view["flights"]["options"][0]
    assert view["flights"]["test_data"] is True and view["top_pick"] is None and view["sections"] == []
    assert row["price_text"] == "$310.00" and row["ticketing"] == "separate"
    assert row["slices"][0]["flight_numbers"] == ["DL 300"]
    assert row["warning"] == flights.SEPARATE_TICKETS_WARNING
    text = chat_flow.format_result(result, task_id=uuid4(), title="Flights", column="review")
    assert "TEST DATA" in text
    assert "Cheapest: $310.00 · Delta · SFO 7:05am → JFK 3:40pm, nonstop / JFK 7:05am → SFO 3:40pm, nonstop" in text
    assert "separate tickets" in text


def test_flight_line_with_bags_and_stops():
    option = {
        "label": None, "total_amount": "200.00", "true_total_amount": "245.00", "currency": "USD",
        "carriers": ["United"], "ticketing": "single", "warnings": [],
        "slices": [{"origin": "SFO", "destination": "JFK", "departing_at": "2026-11-12T13:05:00",
                    "arriving_at": "2026-11-12T23:40:00", "stops": 2, "duration_minutes": 400, "segments": []}],
    }
    assert chat_flow._flight_line(option) == (
        "Option: $200.00 ($245.00 with bags) · United · SFO 1:05pm → JFK 11:40pm, 2 stops"
    )
    assert chat_flow._clock("junk") == ""
    assert chat_flow.flights_view({"options": []}) is None


@pytest.mark.asyncio
async def test_duffel_client_retries_once_then_reports_the_error(monkeypatch):
    monkeypatch.setattr(flights.asyncio, "sleep", AsyncMock())
    calls = {"n": 0}

    def busy_then_ok(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={})
        return httpx.Response(200, json={"data": [{"iata_code": "SFO"}]})

    client = flights.DuffelClient("duffel_test_x", transport=httpx.MockTransport(busy_then_ok))
    assert await client.places(query="SFO") == [{"iata_code": "SFO"}]
    await client.aclose()

    client = flights.DuffelClient("duffel_test_x", transport=httpx.MockTransport(
        lambda r: httpx.Response(503, text="down")))
    with pytest.raises(flights.DuffelError, match="HTTP 503"):
        await client.offer("off_1")
    await client.aclose()

    client = flights.DuffelClient("duffel_test_x", transport=httpx.MockTransport(
        lambda r: httpx.Response(422, json={"errors": [{"title": "Invalid slices"}]})))
    with pytest.raises(flights.DuffelError, match="Invalid slices"):
        await client.places(query="X")
    await client.aclose()


@pytest.mark.asyncio
async def test_a_failed_nearby_lookup_just_searches_the_airports_asked_for():
    def handler(request):
        if request.url.path == "/places/suggestions":
            return httpx.Response(400, json={"errors": [{"message": "bad"}]})
        return httpx.Response(200, json={"data": {"offers": _simple_offers(tuple(
            (s["origin"], s["destination"], s["departure_date"])
            for s in json.loads(request.content)["data"]["slices"]))}})

    session = flights.FlightSession("duffel_test_x", transport=httpx.MockTransport(handler), today=TODAY)
    out = await session.search({**ROUND_TRIP, "return_date": None, "nearby_airports": True})
    assert out["offer_requests"] == 1 and out["options"]


@pytest.mark.asyncio
async def test_unpriceable_bags_are_flagged_not_guessed():
    offer = _offer("cheap", "100.00", _nonstop("a", "SFO", "JFK", "2026-11-12"))
    offer["available_services"] = []  # the airline lists no bag to buy
    duffel = FakeDuffel(lambda key: [offer], offers_by_id={"cheap": offer})
    session = duffel.session()
    await session.search({**ROUND_TRIP, "return_date": None, "checked_bags": 1})
    option = session.option("cheap")
    assert option["true_total_amount"] is None
    assert option["bag_note"] == "Bag fees not priced; check with the airline"
