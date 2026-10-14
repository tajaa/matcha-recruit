"""Ordering findings: hard limits act on verified facts only."""
from app.matcha.services.matcha_work.agent_tasks.research import ranking

from ._fixtures import PLAN, price


def _item(i, fields, **over):
    return {"id": f"i{i}", "fields": fields, "status": "verified", "fit_score": 3, "user_state": "new", **over}


def test_check_each_op():
    c = ranking.check
    assert c({"field": "price", "op": "lte", "value": 3500, "unit": "month"}, price(3200)) == "ok"
    assert c({"field": "price", "op": "lte", "value": 3000}, price(3200)) == "violates"
    assert c({"field": "price", "op": "lte", "value": 3500, "unit": "night"}, price(3200)) == "unknown"
    assert c({"field": "price", "op": "lte", "value": 3500, "currency": "EUR"}, price(3200)) == "unknown"
    assert c({"field": "price", "op": "lte", "value": 3500}, price(3200, status="claimed")) == "unknown"
    assert c({"field": "price", "op": "lte", "value": 3500}, None) == "unknown"
    assert c({"field": "rating", "op": "gte", "value": 4}, {"value": 4.5, "status": "verified"}) == "ok"
    assert c({"field": "beds", "op": "eq", "value": 1}, {"value": 2, "status": "verified"}) == "violates"
    pets = {"value": ["cats"], "status": "verified"}
    assert c({"field": "pets", "op": "includes", "value": ["dogs"]}, pets) == "unknown"
    assert c({"field": "pets", "op": "includes", "value": ["dogs"]}, {"value": ["none"], "status": "verified"}) == "violates"
    assert c({"field": "pets", "op": "includes", "value": "dogs"}, {"value": ["dogs"], "status": "verified"}) == "ok"
    assert c({"field": "amenities", "op": "excludes", "value": ["doorman"]}, {"value": ["doorman"], "status": "verified"}) == "violates"
    assert c({"field": "amenities", "op": "excludes", "value": ["doorman"]}, {"value": ["gym"], "status": "verified"}) == "ok"
    assert c({"field": "neighborhood", "op": "includes", "value": "mission"}, {"value": "Mission", "status": "verified"}) == "ok"
    assert c({"field": "neighborhood", "op": "excludes", "value": "mission"}, {"value": "Mission", "status": "verified"}) == "violates"
    assert c({"field": "in_stock", "op": "is_true", "value": True}, {"value": False, "status": "verified"}) == "violates"
    when = {"value": "2026-11-01", "status": "verified"}
    assert c({"field": "available_date", "op": "before", "value": "2026-11-15"}, when) == "ok"
    assert c({"field": "available_date", "op": "after", "value": "2026-11-15"}, when) == "violates"
    assert c({"field": "available_date", "op": "after", "value": "soon"}, when) == "unknown"
    assert c({"field": "nope", "op": "eq", "value": 1}, when) == "unknown"
    assert c({"field": "beds", "op": "includes", "value": 1}, {"value": 1, "status": "verified"}) == "unknown"


def test_describe_reads_like_a_person():
    d = ranking.describe
    assert d({"field": "price", "op": "lte", "value": 3500.0, "unit": "month"}) == "Price at most $3,500/mo"
    assert d({"field": "pets", "op": "includes", "value": ["dogs"]}) == "Pets includes Dogs OK"
    assert d({"field": "in_stock", "op": "is_true"}) == "In stock: yes"
    assert d({"field": "in_stock", "op": "is_false"}) == "In stock: no"
    assert d({"field": "available_date", "op": "before", "value": "2026-11-01"}) == "Available by Nov 1, 2026"
    assert d({"field": "available_date", "op": "before", "value": "bad"}) == "Available by bad"
    assert d({"field": "nope", "op": "eq"}) == ""


def test_bands_then_score_then_fit():
    items = [
        _item(1, {"price": price(3400), "pets": {"value": ["dogs"], "status": "verified"}}),
        _item(2, {"price": price(3000), "pets": {"value": ["dogs"], "status": "verified"}}),
        _item(3, {"price": price(2500)}),                                    # pets unconfirmed
        _item(4, {"price": price(3900), "pets": {"value": ["dogs"], "status": "verified"}}),  # too dear
        _item(5, {"price": price(2000)}, status="unavailable"),
        _item(6, {"price": price(2100)}, user_state="dismissed"),
        _item(7, {"price": price(2200)}, status="irrelevant"),
    ]
    ranked = {r.item_id: r for r in ranking.rank(items, PLAN)}
    order = [r.item_id for r in sorted(ranked.values(), key=lambda r: r.rank)]
    assert order[:3] == ["i2", "i1", "i3"]
    assert ranked["i3"].band == ranking.UNCONFIRMED and "unconfirmed:pets" in ranked["i3"].explain["flags"]
    assert ranked["i4"].band == ranking.HIDDEN and ranked["i4"].explain["violations"][0]["field"] == "price"
    for hidden, flag in (("i5", "unavailable"), ("i6", "dismissed"), ("i7", "irrelevant")):
        assert ranked[hidden].band == ranking.HIDDEN and flag in ranked[hidden].explain["flags"]
    assert ranked["i2"].explain["parts"]["price"] > ranked["i1"].explain["parts"]["price"]


def test_no_preferences_ranks_by_fit_and_keeps_order():
    items = [_item(1, {}, fit_score=None), _item(2, {}, fit_score=5), _item(3, {}, fit_score=2)]
    ranked = ranking.rank(items, {"constraints": [], "preferences": [], "fit_weight": 0})
    assert [r.item_id for r in ranked] == ["i2", "i3", "i1"] and all(r.score == 0 for r in ranked)
    prefs = {"preferences": [{"field": "beds", "weight": 1, "higher_is_better": False},
                             {"field": "available_date", "weight": 1}, {"field": "pets", "weight": 1},
                             {"field": "in_stock", "weight": 1}, {"field": "nope", "weight": 1},
                             {"field": "neighborhood", "weight": 1}]}
    same = [_item(1, {"beds": {"value": 1, "status": "verified"},
                      "available_date": {"value": "bad", "status": "verified"},
                      "pets": {"value": ["dogs"], "status": "verified"},
                      "in_stock": {"value": True, "status": "claimed"},
                      "neighborhood": {"value": "x", "status": "verified"}})]
    [only] = ranking.rank(same, prefs)
    assert only.explain["parts"]["beds"] == 1.0
