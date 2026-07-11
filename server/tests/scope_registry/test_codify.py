"""codify layer pure core — match_codifications + group_research_units. No DB."""
from app.core.services.scope_registry.codify import (
    build_citation_stamps,
    build_research_context,
    group_research_units,
    match_codifications,
    select_primary_citation,
)


def _item(key, category, level, cite="X", heading="h"):
    return {"regulation_key": key, "category_slug": category, "level": level,
            "citation": cite, "heading": heading}


def test_group_research_units_by_jurisdiction_and_category():
    items = [
        _item("daily_weekly_overtime", "overtime", "federal"),
        _item("national_minimum_wage", "minimum_wage", "federal"),
        _item("state_paid_sick_leave", "sick_leave", "state"),
    ]
    units = group_research_units(items, federal_id="F", state_id="S", city_id=None)
    by_jur = {u["jurisdiction_id"]: u for u in units}
    assert set(by_jur) == {"F", "S"}
    assert set(by_jur["F"]["categories"]) == {"overtime", "minimum_wage"}
    assert by_jur["S"]["categories"] == ["sick_leave"]


def test_group_city_falls_back_to_state_without_city_row():
    items = [_item("local_sick_leave", "sick_leave", "city")]
    units = group_research_units(items, federal_id="F", state_id="S", city_id=None)
    assert len(units) == 1 and units[0]["jurisdiction_id"] == "S"
    # with a city row it targets the city
    units2 = group_research_units(items, federal_id="F", state_id="S", city_id="C")
    assert units2[0]["jurisdiction_id"] == "C"


def test_group_drops_items_without_target_or_category():
    items = [
        _item("k1", "overtime", "state"),           # ok
        _item("k2", None, "state"),                 # no RKD category → dropped
        _item("k3", "overtime", "federal"),         # no federal_id → dropped
    ]
    units = group_research_units(items, federal_id=None, state_id="S", city_id=None)
    assert len(units) == 1
    assert units[0]["keys"] == ["k1"]


def test_build_research_context_targets_the_keys():
    ctx = build_research_context([_item("meal_break", "meal_breaks", "state",
                                        cite="Lab 512", heading="Meal periods")])
    assert "meal_break" in ctx and "Lab 512" in ctx and "not yet codified" in ctx


def _cls(id, key, kd=None):
    return {"id": id, "regulation_key": key, "key_definition_id": kd}


def _req(id, key, jur="J", category="minimum_wage"):
    return {"id": id, "regulation_key": key, "jurisdiction_id": jur, "category": category}


def test_match_by_key_equality():
    links = match_codifications(
        [_cls("c1", "state_minimum_wage")],
        [_req("r1", "state_minimum_wage")],
    )
    assert len(links) == 1
    assert links[0] == {
        "classification_id": "c1", "jurisdiction_requirement_id": "r1",
        "regulation_key": "state_minimum_wage", "jurisdiction_id": "J",
    }


def test_null_key_classification_never_matches():
    links = match_codifications(
        [_cls("c1", None), _cls("c2", "")],
        [_req("r1", "state_minimum_wage")],
    )
    assert links == []


def test_no_catalog_row_leaves_unmatched():
    links = match_codifications([_cls("c1", "fmla")], [_req("r1", "state_minimum_wage")])
    assert links == []


def test_category_guard_via_rkd():
    # exempt_salary_threshold lives under both minimum_wage and overtime in RKD.
    # A classification tagged (via key_definition_id) to the minimum_wage RKD row
    # must only link the minimum_wage catalog row, not the overtime one.
    links = match_codifications(
        [_cls("c1", "exempt_salary_threshold", kd="kd_mw")],
        [
            _req("r_mw", "exempt_salary_threshold", category="minimum_wage"),
            _req("r_ot", "exempt_salary_threshold", category="overtime"),
        ],
        rkd_category_by_id={"kd_mw": "minimum_wage"},
    )
    assert {l["jurisdiction_requirement_id"] for l in links} == {"r_mw"}


def test_no_key_definition_id_matches_all_categories():
    # Without a kd hint, the guard is off — key equality alone.
    links = match_codifications(
        [_cls("c1", "exempt_salary_threshold")],
        [
            _req("r_mw", "exempt_salary_threshold", category="minimum_wage"),
            _req("r_ot", "exempt_salary_threshold", category="overtime"),
        ],
    )
    assert {l["jurisdiction_requirement_id"] for l in links} == {"r_mw", "r_ot"}


def test_multi_jurisdiction_one_link_per_pair():
    # Same key codified at two levels → one link per catalog row.
    links = match_codifications(
        [_cls("c1", "state_paid_sick_leave")],
        [
            _req("r_state", "state_paid_sick_leave", jur="CA"),
            _req("r_city", "state_paid_sick_leave", jur="SF"),
        ],
    )
    assert len(links) == 2
    assert {l["jurisdiction_id"] for l in links} == {"CA", "SF"}


# ── select_primary_citation ────────────────────────────────────────────────

def _cand(cite, item_id="i", level="federal", src="ecfr", hier=None):
    return {"item_id": item_id, "citation": cite, "jurisdiction_level": level,
            "source_type": src, "hierarchy": hier or {}}


def test_select_primary_empty_is_none():
    assert select_primary_citation([]) is None


def test_select_primary_level_match_beats_regulation():
    # A state statute should win over a federal regulation when the requirement
    # is a state row — jurisdiction match is the top rule.
    cands = [
        _cand("29 CFR 541.600", level="federal", src="ecfr"),
        _cand("Cal. Lab. Code § 515", level="state", src="curated"),
    ]
    got = select_primary_citation(cands, requirement_level="state")
    assert got["citation"] == "Cal. Lab. Code § 515"


def test_select_primary_regulation_over_statute_same_level():
    # 29 CFR 541.600 (regulation, carries the dollar amount) beats 29 U.S.C. 213.
    cands = [
        _cand("29 U.S.C. § 213", level="federal", src="ecfr"),
        _cand("29 CFR § 541.600", level="federal", src="ecfr"),
    ]
    got = select_primary_citation(cands, requirement_level="federal")
    assert got["citation"] == "29 CFR § 541.600"


def test_select_primary_deeper_hierarchy_wins():
    cands = [
        _cand("29 CFR 541", hier={"title": "29", "part": "541"}),
        _cand("29 CFR 541.600", hier={"title": "29", "part": "541", "section": "600"}),
    ]
    got = select_primary_citation(cands, requirement_level="federal")
    assert got["citation"] == "29 CFR 541.600"


def test_select_primary_lexicographic_tiebreak_is_deterministic():
    cands = [_cand("29 CFR 500.2"), _cand("29 CFR 500.1")]
    assert select_primary_citation(cands, requirement_level="federal")["citation"] == "29 CFR 500.1"


# ── build_citation_stamps ──────────────────────────────────────────────────

def _link(rid, item_id, cite, src="ecfr", level="federal", slug="us-flsa"):
    return {"jurisdiction_requirement_id": rid, "classification_id": "c",
            "item_id": item_id, "citation": cite, "hierarchy": {},
            "index_slug": slug, "source_type": src, "jurisdiction_level": level}


def test_stamp_multi_classification_primary_plus_full_set():
    links = [
        _link("r1", "i_usc", "29 U.S.C. § 213"),
        _link("r1", "i_cfr", "29 CFR § 541.600"),
    ]
    stamps = build_citation_stamps(links, {"r1": "federal"})
    assert stamps["r1"]["statute_citation"] == "29 CFR § 541.600"  # regulation wins
    assert stamps["r1"]["citation_item_id"] == "i_cfr"
    cites = [v["citation"] for v in stamps["r1"]["verified_citations"]]
    assert cites == ["29 CFR § 541.600", "29 U.S.C. § 213"]  # sorted, full set


def test_stamp_dedupes_same_item_reached_twice():
    links = [_link("r1", "i_cfr", "29 CFR § 541.600"),
             _link("r1", "i_cfr", "29 CFR § 541.600")]
    stamps = build_citation_stamps(links, {"r1": "federal"})
    assert len(stamps["r1"]["verified_citations"]) == 1


def test_stamp_skips_links_without_item_or_citation():
    links = [{"jurisdiction_requirement_id": "r1", "item_id": None, "citation": None}]
    assert build_citation_stamps(links, {}) == {}
