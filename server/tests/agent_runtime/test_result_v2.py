import pytest

from app.matcha.services.matcha_work.agent_runtime import result
from app.matcha.services.matcha_work.agent_runtime.abilities import shopping, web
from app.matcha.services.matcha_work.agent_runtime.context import RunState

from .helpers import ability


async def _fetch(url):
    return {}, set()


def _abilities():
    return [web.build(fetch_page=_fetch, max_fetches=1, fetch_seconds=1), shopping.build()]


def _state(*urls):
    return RunState(started=0.0, provenance=set(urls))


PICK = {
    "name": "Standing Desk", "why": ["Sturdy"],
    "price": {"amount": 449, "currency": "usd", "source_url": "https://shop.example/desk"},
    "buy_links": [{"retailer": "Shop", "url": "https://shop.example/desk"},
                  {"retailer": "Fake", "url": "https://invented.example/desk"}],
}


def test_the_finish_tool_offers_the_blocks_of_the_enabled_abilities():
    tool = result.finish_tool(_abilities())
    blocks = tool.parameters["properties"]["blocks"]
    assert blocks["items"]["properties"]["type"]["enum"] == ["picks", "sections", "sources"]
    assert {"top_pick", "alternatives", "sections", "sources"} <= set(blocks["items"]["properties"])
    assert tool.effect == "finish" and tool.name == "finish"
    none = result.finish_tool([])
    assert none.parameters["properties"]["blocks"]["items"]["properties"]["type"]["enum"] == ["none"]


def test_headline_and_summary_are_required():
    for bad in ({}, {"headline": "x"}, {"summary": "y"}, "nope", {"headline": " ", "summary": " "}):
        with pytest.raises(ValueError):
            result.normalize(bad, _state(), _abilities())


def test_picks_and_flights_use_the_v1_gates():
    out, warnings = result.normalize({
        "headline": "Desk", "summary": "The sturdy one.", "confidence": "high",
        "blocks": [{"type": "picks", "top_pick": PICK, "alternatives": []}],
    }, _state("https://shop.example/desk"), _abilities())
    pick = out["blocks"][0]["top_pick"]
    assert [l["url"] for l in pick["buy_links"]] == ["https://shop.example/desk"]
    assert pick["price"] == {"amount": 449.0, "currency": "USD", "source_url": "https://shop.example/desk"}
    assert any("invented.example" in w for w in warnings)
    assert out["schema"] == "agent_result.v2" and out["confidence"] == "high"


def test_sections_and_sources_are_gated():
    out, warnings = result.normalize({
        "headline": "H", "summary": "S", "caveats": ["one", "", 3],
        "blocks": [
            {"type": "sections", "sections": [
                {"heading": "Why", "body_md": "See [the page](https://a.example/x) and [this](https://evil.example)."}]},
            {"type": "sources", "sources": [{"title": "A", "url": "https://a.example/x"},
                                            {"title": "B", "url": "https://unseen.example"}]},
        ],
    }, _state("https://a.example/x"), _abilities())
    sections, sources = out["blocks"]
    assert "[the page](https://a.example/x)" in sections["sections"][0]["body_md"]
    assert "evil.example" not in sections["sections"][0]["body_md"]
    assert sources["sources"] == [{"title": "A", "url": "https://a.example/x"}]
    assert out["caveats"] == ["one", "3"] and out["confidence"] == "low"
    assert warnings


def test_a_block_type_no_enabled_ability_owns_is_dropped():
    out, warnings = result.normalize({
        "headline": "H", "summary": "S",
        "blocks": [{"type": "emails", "message_ids": ["m1"]}, {"type": ""}, "junk",
                   {"type": "picks", "top_pick": None, "alternatives": []}],
    }, _state(), _abilities())
    assert out["blocks"] == []
    assert any("emails" in w for w in warnings) and any("untyped" in w for w in warnings)


def test_a_second_block_of_a_type_is_dropped_and_blocks_are_capped():
    sections = {"type": "sections", "sections": [{"heading": "A", "body_md": "text"}]}
    out, warnings = result.normalize(
        {"headline": "H", "summary": "S", "blocks": [sections, sections]}, _state(), _abilities(),
    )
    assert len(out["blocks"]) == 1 and any("second sections" in w for w in warnings)

    many = [ability(key=f"a{i}", block_schemas={f"b{i}": {}},
                    gate=lambda kind, raw, state: ({"ok": True}, [])) for i in range(10)]
    out, warnings = result.normalize(
        {"headline": "H", "summary": "S", "blocks": [{"type": f"b{i}"} for i in range(10)]},
        _state(), many,
    )
    assert len(out["blocks"]) == result.MAX_BLOCKS and any("Trimmed" in w for w in warnings)


def test_a_block_that_is_not_an_object_is_dropped_by_its_gate():
    for kind in ("picks", "sections"):
        block, warnings = (shopping.gate_block if kind == "picks" else web.gate_block)(kind, "nope", _state())
        assert block is None and warnings


def test_read_result_views_v1_as_v2():
    v1 = {"schema": "agent_result.v1", "headline": "H", "summary": "S", "confidence": "medium",
          "top_pick": {"name": "X"}, "alternatives": [], "criteria": [{"name": "c"}],
          "sections": [{"heading": "h", "body_md": "b"}], "sources": [{"title": "t", "url": "u"}],
          "flights": {"offers": []}, "warnings": ["w"], "caveats": ["c"]}
    view = result.read_result(v1)
    assert view["schema"] == "agent_result.v2"
    assert [b["type"] for b in view["blocks"]] == ["picks", "flights", "sections", "sources"]
    assert view["blocks"][0]["top_pick"] == {"name": "X"} and view["warnings"] == ["w"]
    flights = result.read_result({"headline": "H", "summary": "S", "flights": {"offers": [1]}})
    assert flights["blocks"] == [{"type": "flights", "flights": {"offers": [1]}}]
    v2 = {"schema": "agent_result.v2", "headline": "H", "blocks": []}
    assert result.read_result(v2) is v2
    assert result.read_result(None) is None and result.read_result("x") is None


def test_the_chat_view_is_bounded_and_carries_no_unsafe_links():
    stored = {
        "schema": "agent_result.v2", "headline": "H" * 400, "summary": "S" * 2000, "confidence": "high",
        "caveats": ["c"] * 9,
        "blocks": [
            {"type": "picks", "top_pick": {"name": "Desk", "brand": "B", "why": ["a"], "price": None,
                                           "rating": None, "reviews": [], "images": [], "buy_links": []},
             "alternatives": [{"name": f"Alt {i}", "why": [], "price": None, "rating": None,
                               "reviews": [], "images": [], "buy_links": []} for i in range(5)]},
            {"type": "sections", "sections": [{"heading": "h", "body_md": "b" * 5000}] * 6},
            {"type": "sources", "sources": [{"title": "ok", "url": "https://a.example"},
                                            {"title": "bad", "url": "javascript:alert(1)"}]},
            {"type": "reservation", "venue": "Nopa", "status": "booked"},
        ],
    }
    view = result.chat_view(stored)
    # `_short` clips to the limit and may add one ellipsis character.
    assert len(view["headline"]) <= 201 and len(view["summary"]) <= 601 and len(view["caveats"]) == 3
    picks, sections, sources, reservation = view["blocks"]
    assert picks["top_pick"]["name"] == "Desk" and len(picks["alternatives"]) == 3
    assert len(sections["sections"]) == 4 and len(sections["sections"][0]["body_md"]) == 1500
    assert sources["sources"] == [{"title": "ok", "url": "https://a.example"}]
    assert reservation == {"type": "reservation", "venue": "Nopa", "status": "booked"}
    assert result.picks_block(stored)["top_pick"]["name"] == "Desk"
    assert result.picks_block({"blocks": [{"type": "sections"}]}) is None


def test_the_text_fallback_has_the_answer_and_never_is_empty():
    assert result.text_fallback({"headline": "Booked", "summary": "Friday at 7."}) == "Booked\n\nFriday at 7."
    assert result.text_fallback({}) == "Done."
