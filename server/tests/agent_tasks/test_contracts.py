"""What the model hands back, and what survives the checks."""
import pytest

from app.matcha.services.matcha_work.agent_tasks.research import contracts as C

from ._fixtures import TODAY

BRIEF = {"location": "San Francisco", "budget_max": 3500, "currency": "USD", "must_haves": ["dogs"],
         "needed_by": "2026-12-01"}


def _plan_args(**over):
    result = {
        "title": "1bd SF", "item_kind": "listing", "source": "web",
        "queries": ["1 bedroom apartment dogs", "1 bedroom apartment dogs", "x", "1br Mission San Francisco"],
        "fields": ["price", "beds", "nope"],
        "constraints": [{"field": "price", "op": "lte", "value": 4000, "unit": "month"},
                        {"field": "pets", "op": "includes", "value": ["dogs"], "unit": None},
                        {"field": "beds", "op": "includes", "value": 1, "unit": None},
                        {"field": "in_stock", "op": "is_true", "value": True, "unit": None},
                        {"field": "neighborhood", "op": "includes", "value": "", "unit": None},
                        "junk"],
        "preferences": [{"field": "price", "weight": 2, "higher_is_better": False},
                        {"field": "neighborhood", "weight": 1}, {"field": "sqft", "weight": 0}, "junk",
                        {"field": "beds", "weight": True}],
        "fit_weight": 0.5, "prefer_sources": ["the building's own site", ""], "summary": "A 1bd",
    }
    return {"result": {**result, **over}}


def test_plan_keeps_the_persons_limits():
    plan, warnings = C.normalize_plan(_plan_args(), brief=BRIEF, today=TODAY)
    assert plan["queries"][0] == "1 bedroom apartment dogs San Francisco"
    assert plan["queries"][-1] == "1br Mission San Francisco" and len(plan["queries"]) == 2
    price = [c for c in plan["constraints"] if c["field"] == "price"]
    # Generic research: the budget has no unit, so it compares with a price in
    # any unit (a home to buy isn't read as a monthly rent). Apartments say month.
    assert price == [{"field": "price", "op": "lte", "value": 3500.0, "currency": "USD", "source": "brief"}]
    from app.matcha.services.matcha_work.agent_tasks.research import kinds

    rent, _ = C.normalize_plan(_plan_args(), brief=BRIEF, today=TODAY, kind=kinds.APARTMENTS)
    assert [c.get("unit") for c in rent["constraints"] if c["field"] == "price"] == ["month"]
    assert any(c["field"] == "available_date" and c["op"] == "before" for c in plan["constraints"])
    assert any(c == {"field": "in_stock", "op": "is_true", "value": True} for c in plan["constraints"])
    assert len(warnings) == 3  # beds/includes, empty text, junk
    assert plan["preferences"] == [{"field": "price", "weight": 1.0, "higher_is_better": False}]
    assert plan["fields"][:2] == ["price", "beds"] and "pets" in plan["fields"]
    assert plan["must_haves"] == ["dogs"] and plan["fit_weight"] == 0.5 and plan["prefer_sources"] == ["the building's own site"]
    other, _ = C.normalize_plan(_plan_args(item_kind="weird", source="weird", fit_weight="x", fields=[],
                                           constraints=[], preferences=[]), brief={}, today=TODAY)
    assert other["item_kind"] == "other" and other["source"] == "web" and other["fit_weight"] == 0.3
    assert other["fields"] == ["price"]
    with pytest.raises(ValueError):
        C.normalize_plan(_plan_args(queries=["", "x"]), brief={}, today=TODAY)
    with pytest.raises(ValueError):
        C.normalize_plan({"result": "no"}, brief={}, today=TODAY)


def test_a_text_limit_given_as_a_list_reads_as_its_text():
    clean = C.clean_constraint
    assert clean({"field": "neighborhood", "op": "includes", "value": ["Mission", "x"]}, today=TODAY)["value"] == "Mission"
    assert clean({"field": "neighborhood", "op": "includes", "value": [1, " "]}, today=TODAY) is None
    assert clean({"field": "neighborhood", "op": "includes", "value": {"a": 1}}, today=TODAY) is None


def test_fallback_plan_searches_the_directive():
    plan = C.plan_from_brief("best organic   lip balm", {"budget_max": 15}, today=TODAY)
    assert plan["queries"] == ["best organic lip balm"] and plan["origin"] == "fallback"
    assert plan["constraints"][0]["value"] == 15.0 and "unit" not in plan["constraints"][0]


def _cand(**over):
    return {"title": "Sunny 1BR", "subtitle": "Mission", "url": "https://apts.test/1", "image_url": None,
            "facts": [], **over}


def test_candidates_need_seen_links_and_quoted_facts():
    page = "Sunny 1BR. Rent is $3,200 a month. Dogs welcome."
    review = "Our review: the Sunny 1BR rents for $3,100 a month."
    args = {"result": {"candidates": [
        _cand(image_url="https://img.test/a.jpg", facts=[
            {"field": "price", "value": 3200, "quote": "Rent is $3,200 a month", "source_url": "https://apts.test/1"},
            {"field": "pets", "value": ["dogs"], "quote": "Dogs welcome", "source_url": "https://www.apts.test/1/"},
            {"field": "beds", "value": 2, "quote": "Rent is $3,200 a month", "source_url": "https://apts.test/1"},
            {"field": "sqft", "value": 650, "quote": "650 sq ft", "source_url": "https://apts.test/1"},
            {"field": "nope", "value": 1, "quote": "x", "source_url": "https://apts.test/1"},
            {"field": "price", "value": "n/a", "quote": "x", "source_url": "https://apts.test/1"},
            {"field": "price", "value": 3100, "quote": "rents for $3,100 a month", "source_url": "https://blog.test/r"},
            {"field": "price", "value": 3100, "quote": "rents for $3,100", "source_url": "https://other.test/x"},
            "junk",
        ]),
        _cand(title="Made up", url="https://never.test/x"),
        _cand(),  # a repeat
        "junk",
    ]}}
    citable = {"https://apts.test/1", "https://blog.test/r"}
    out, warnings = C.normalize_candidates(
        args, plan={"item_kind": "listing"}, citable=citable,
        pages={"https://apts.test/1": page, "https://blog.test/r": review},
        images={"https://img.test/a.jpg": "https://apts.test/1"}, today=TODAY,
    )
    assert len(out) == 1
    [found] = out
    assert found["fields"]["price"]["status"] == "verified" and found["fields"]["price"]["value"] == 3200
    assert found["fields"]["pets"]["status"] == "verified"
    assert set(found["fields"]) == {"price", "pets"}
    assert found["image_candidates"] == [{"source_url": "https://img.test/a.jpg",
                                          "page_url": "https://apts.test/1", "alt": "Sunny 1BR"}]
    assert any("never seen" in w for w in warnings) and len(warnings) >= 6
    # The claim from another page is kept only as claimed.
    only_review = {"result": {"candidates": [_cand(facts=[
        {"field": "price", "value": 3100, "quote": "rents for $3,100 a month", "source_url": "https://blog.test/r"}])]}}
    out, _ = C.normalize_candidates(only_review, plan={"item_kind": "x"}, citable=citable,
                                    pages={"https://blog.test/r": review}, images={}, today=TODAY)
    assert out[0]["fields"]["price"]["status"] == "claimed" and out[0]["kind"] == "other"


def test_screen_maps_short_ids():
    batch = {"F1": "a", "F2": "b"}
    verdicts, warnings = C.normalize_screen({"result": {"verdicts": [
        {"id": "f1", "relevant": True, "fit": 9, "reasons": ["Near BART", ""]},
        {"id": "F2", "relevant": False, "fit": "x", "reasons": []},
        {"id": "F9", "relevant": True, "fit": 1, "reasons": []}, "junk",
    ]}}, batch)
    assert verdicts["a"] == {"relevant": True, "fit": 5, "reasons": ["Near BART"]}
    assert verdicts["b"]["fit"] is None and warnings
    with pytest.raises(ValueError):
        C.normalize_screen({"result": {"verdicts": []}}, batch)


def test_summary_numbers_come_from_the_findings():
    batch = {"F1": "a", "F2": "b"}
    texts = {"a": "Sunny 1BR $3,200/mo 3200", "b": "Loft $3,400/mo"}
    citable = {"https://apts.test/1"}
    ok, warnings = C.normalize_summary({"result": {
        "headline": "Two 1BRs that take dogs", "summary": "The cheapest is $3,200 a month.",
        "sections": [{"heading": "Notes", "body_md": "See [it](https://apts.test/1) and [this](https://evil.test)"},
                     {"heading": "Bad", "body_md": "Rents start at $2,100"}],
        "top": [{"id": "F1", "why": "Cheapest at $3,200"}, {"id": "F2", "why": "Has $9,999 of upgrades"},
                {"id": "F1", "why": "dup"}, {"id": "F7", "why": "x"}, "junk"],
    }}, batch=batch, item_texts=texts, citable=citable)
    assert ok["top"] == [{"item_id": "a", "why": "Cheapest at $3,200"}, {"item_id": "b", "why": ""}]
    assert len(ok["sections"]) == 1 and "evil" not in ok["sections"][0]["body_md"]
    assert any("Dropped section" in w for w in warnings)
    with pytest.raises(ValueError) as exc:
        C.normalize_summary({"result": {"headline": "From $1,999!", "summary": "", "sections": [], "top": []}},
                            batch=batch, item_texts=texts, citable=citable)
    assert "1,999" in str(exc.value)
    # The person's own limit and the counts may be stated.
    ok, _ = C.normalize_summary({"result": {"headline": "2 of 80 fit under your $3,500 budget", "summary": "",
                                            "sections": [], "top": [{"id": "F2", "why": "Under $3,500"}]}},
                                batch=batch, item_texts=texts, citable=citable, context="Price at most $3,500/mo 80")
    assert ok["top"][0]["why"] == "Under $3,500"
    with pytest.raises(ValueError):
        C.normalize_summary({"result": {"headline": "", "summary": "", "sections": [], "top": []}},
                            batch=batch, item_texts=texts, citable=citable)
    assert C.unsupported_numbers("top 5 for 2 people", "") == []
    named, _ = C.normalize_summary({"result": {"headline": "F1 is the pick", "summary": "F2 and F9 trail.",
                                               "sections": [{"heading": "x", "body_md": "Only F1 has a price"}],
                                               "top": [{"id": "F1", "why": "Beats F2"}]}},
                                   batch=batch, item_texts=texts, citable=citable,
                                   titles={"F1": "Sunny 1BR", "F2": "Loft"})
    assert named["headline"] == "Sunny 1BR is the pick" and named["summary"] == "Loft and F9 trail."
    assert named["sections"][0]["body_md"] == "Only Sunny 1BR has a price" and named["top"][0]["why"] == "Beats Loft"


def test_refine_changes_limits_but_never_loses_one():
    plan, _ = C.normalize_plan(_plan_args(), brief=BRIEF, today=TODAY)
    out, _ = C.normalize_refine({"result": {
        "constraints": [{"field": "pets", "op": "includes", "value": ["dogs"]}],
        "preferences": [], "fields_add": ["sqft", "nope", "price"], "queries": ["1br Mission"],
        "search_again": True, "note": "Only the Mission now",
    }}, plan=plan, brief=BRIEF, today=TODAY)
    new = out["plan"]
    # The budget the model left out is kept.
    assert any(c["field"] == "price" and c["value"] == 3500.0 for c in new["constraints"])
    assert "sqft" in new["fields"] and new["queries"] == ["1br Mission San Francisco"]
    assert out["search_again"] is True and out["note"] == "Only the Mission now"
    raised, _ = C.normalize_refine({"result": {
        "constraints": [{"field": "price", "op": "lte", "value": 4000, "unit": "month"}],
        "preferences": [], "fields_add": [], "queries": [], "search_again": False, "note": "",
    }}, plan=plan, brief=BRIEF, today=TODAY)
    prices = [c for c in raised["plan"]["constraints"] if c["field"] == "price"]
    assert prices == [{"field": "price", "op": "lte", "value": 4000.0, "unit": "month"}]
    assert raised["plan"]["queries"] == plan["queries"]


def test_a_query_that_already_says_where_isnt_given_the_place_again():
    assert C.names_place("1br Mission District San Francisco dogs", "Mission District, San Francisco")
    assert not C.names_place("1br Mission dogs", "Mission District, San Francisco")
    plan = C.plan_from_brief("1 bedroom Mission District San Francisco", {"location": "Mission District, San Francisco"},
                             today=TODAY)
    assert plan["queries"] == ["1 bedroom Mission District San Francisco"]
    plan = C.plan_from_brief("1 bedroom dogs", {"location": "Mission District, San Francisco"}, today=TODAY)
    assert plan["queries"] == ["1 bedroom dogs Mission District, San Francisco"]
