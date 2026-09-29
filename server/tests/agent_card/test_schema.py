import pytest

from app.matcha.services.matcha_work.agent_card.schema import (
    MAX_ALTERNATIVES,
    normalize_result,
    normalize_url,
)

SEEN = {
    "https://www.brand.example/products/balm?utm_source=google",
    "https://reviews.example/best-lip-balm",
    "https://shop.example/balm",
}


def _pick(**over):
    pick = {
        "name": "Organic Balm",
        "brand": "Brand",
        "why": ["USDA organic", "no fragrance"],
        "price": {"amount": 4.99, "currency": "usd", "source_url": "https://shop.example/balm"},
        "rating": {"value": 4.7, "scale": 5, "count": 1200, "source_url": "https://shop.example/balm/"},
        "reviews": [{"quote": "Best balm I've used.", "source_name": "Reviews", "url": "https://reviews.example/best-lip-balm", "sentiment": "pos"}],
        "images": [{"source_url": "https://cdn.shop.example/balm.jpg", "page_url": "https://shop.example/balm", "alt": "tube"}],
        "buy_links": [{"retailer": "Shop", "url": "https://brand.example/products/balm#buy", "price": 4.99}],
    }
    pick.update(over)
    return pick


def _raw(**over):
    raw = {
        "headline": "Organic Balm is the pick",
        "summary": "It wins on ingredients and price.",
        "answer_type": "recommendation",
        "top_pick": _pick(),
        "alternatives": [],
        "sources": [{"title": "Roundup", "url": "https://reviews.example/best-lip-balm"}],
        "confidence": "high",
    }
    raw.update(over)
    return raw


def test_normalize_url_ignores_www_tracking_fragment_and_trailing_slash():
    assert normalize_url("https://www.Brand.example/products/balm/?utm_source=x&gclid=1#top") == \
        normalize_url("http://brand.example/products/balm")
    assert normalize_url("javascript:alert(1)") is None
    assert normalize_url(None) is None


def test_traced_links_survive_and_fields_are_coerced():
    result, warnings = normalize_result(_raw(), SEEN)
    pick = result["top_pick"]
    assert warnings == []
    assert result["schema"] == "agent_result.v1"
    assert pick["price"] == {"amount": 4.99, "currency": "USD", "source_url": "https://shop.example/balm"}
    assert pick["rating"]["value"] == 4.7 and pick["rating"]["count"] == 1200
    assert len(pick["buy_links"]) == 1 and len(pick["reviews"]) == 1 and len(pick["images"]) == 1
    assert result["sources"][0]["url"] == "https://reviews.example/best-lip-balm"


def test_links_the_run_never_saw_are_dropped_with_warnings():
    raw = _raw(top_pick=_pick(
        buy_links=[{"retailer": "Made up", "url": "https://invented.example/buy"}],
        reviews=[{"quote": "Great", "url": "https://invented.example/review"}],
        price={"amount": 3, "currency": "USD", "source_url": "https://invented.example/p"},
        rating={"value": 5, "scale": 5, "source_url": "https://invented.example/r"},
        images=[{"source_url": "https://cdn.example/x.jpg", "page_url": "https://invented.example/p"}],
    ), sources=[{"title": "x", "url": "javascript:alert(1)"}])
    result, warnings = normalize_result(raw, SEEN)
    pick = result["top_pick"]
    assert pick["buy_links"] == [] and pick["reviews"] == [] and pick["images"] == []
    assert pick["price"] is None and pick["rating"] is None
    assert result["sources"] == []
    assert len(warnings) == 6
    assert any("never seen" in w for w in warnings)
    assert any("not an http(s) URL" in w for w in warnings)


def test_alternatives_are_trimmed_and_nameless_picks_dropped():
    alts = [_pick(name=f"Alt {i}") for i in range(MAX_ALTERNATIVES + 2)] + [_pick(name="")]
    result, warnings = normalize_result(_raw(alternatives=alts), SEEN)
    assert len(result["alternatives"]) == MAX_ALTERNATIVES
    assert any("no name" in w for w in warnings)
    assert any("Trimmed" in w for w in warnings)


def test_rating_out_of_scale_is_dropped_and_quote_bounded():
    raw = _raw(top_pick=_pick(
        rating={"value": 9, "scale": 5, "source_url": "https://shop.example/balm"},
        reviews=[{"quote": "x" * 900, "url": "https://reviews.example/best-lip-balm", "sentiment": "weird"}],
    ))
    result, _ = normalize_result(raw, SEEN)
    assert result["top_pick"]["rating"] is None
    review = result["top_pick"]["reviews"][0]
    assert len(review["quote"]) == 280 and review["sentiment"] == "mixed"


def test_answer_type_and_confidence_fall_back():
    result, _ = normalize_result(_raw(top_pick=None, answer_type="bogus", confidence="certain",
                                      sections=[{"heading": "How", "body_md": "Do this."}]), SEEN)
    assert result["answer_type"] == "answer"
    assert result["confidence"] == "low"
    assert result["sections"] == [{"heading": "How", "body_md": "Do this."}]


@pytest.mark.parametrize("raw", [None, [], {"headline": "x"}, {"summary": "y"}])
def test_unusable_payload_raises_for_repair(raw):
    with pytest.raises(ValueError):
        normalize_result(raw, SEEN)


def test_duplicate_sources_collapse():
    result, _ = normalize_result(_raw(sources=[
        {"title": "a", "url": "https://reviews.example/best-lip-balm"},
        {"title": "b", "url": "https://reviews.example/best-lip-balm/?utm_medium=x"},
    ]), SEEN)
    assert len(result["sources"]) == 1


# ── section Markdown (the one free-form field clients render as live Markdown) ──

def _section(body):
    return _raw(sections=[{"heading": "How", "body_md": body}])


def test_section_images_are_removed_never_hotlinked():
    result, warnings = normalize_result(_section(
        "Before ![track](https://evil.example/pixel.png) ![ref][x] after\n\n[x]: https://evil.example/i.png"
    ), SEEN)
    body = result["sections"][0]["body_md"]
    assert "evil.example" not in body and "![" not in body
    assert any("Removed" in w for w in warnings)


def test_section_links_survive_only_when_the_run_saw_them():
    result, _ = normalize_result(_section(
        "[good](https://shop.example/balm) [bad](https://evil.example/x) [js](javascript:alert(1)) "
        "[ref][1] <https://evil.example/auto> https://evil.example/bare. https://shop.example/balm, done\n"
        "[1]: https://evil.example/ref"
    ), SEEN)
    body = result["sections"][0]["body_md"]
    assert "[good](https://shop.example/balm)" in body
    assert "https://shop.example/balm," in body
    for gone in ("evil.example", "javascript", "](", "[1]:"):
        assert gone not in body.replace("[good](https://shop.example/balm)", "")
    assert "bad" in body and "js" in body and "ref" in body  # link text is kept


def test_section_html_is_stripped_and_empty_sections_dropped():
    result, _ = normalize_result(_raw(sections=[
        {"heading": "a", "body_md": "<script>x()</script><b>hi</b>"},
        {"heading": "b", "body_md": "![only](https://evil.example/a.png)"},
    ]), SEEN)
    assert [s["body_md"] for s in result["sections"]] == ["x()hi"]


def test_nested_parens_in_a_hostile_link_leave_no_fragment():
    result, _ = normalize_result(_section("[js](javascript:alert(1)) text"), SEEN)
    assert result["sections"][0]["body_md"] == "js text"
