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


def _sev_item(key, category, level, severity):
    it = _item(key, category, level)
    it["severity"] = severity
    return it


def test_group_units_sorted_most_severe_first():
    # each in its own jurisdiction level → one unit apiece; units order by severity.
    items = [
        _sev_item("a", "sick_leave", "state", "low"),
        _sev_item("b", "overtime", "federal", "critical"),
        _sev_item("c", "min_wage", "city", "high"),
    ]
    units = group_research_units(items, federal_id="F", state_id="S", city_id="C")
    assert [u["jurisdiction_id"] for u in units] == ["F", "C", "S"]
    assert units[0]["severity_rank"] == 0


def test_group_unit_severity_is_its_most_severe_item():
    # two items land in one federal unit; the unit ranks by the worst of them.
    items = [
        _sev_item("a", "overtime", "federal", "moderate"),
        _sev_item("b", "min_wage", "federal", "critical"),
    ]
    units = group_research_units(items, federal_id="F", state_id="S", city_id=None)
    assert len(units) == 1 and units[0]["severity_rank"] == 0
    # within the unit, the critical item sorts ahead of the moderate one.
    assert units[0]["items"][0]["regulation_key"] == "b"


def test_group_none_severity_ranks_as_moderate():
    items = [
        _sev_item("a", "overtime", "federal", None),   # None → moderate band
        _sev_item("b", "min_wage", "state", "low"),
    ]
    units = group_research_units(items, federal_id="F", state_id="S", city_id=None)
    # federal (None→moderate=2) before state (low=3)
    assert [u["jurisdiction_id"] for u in units] == ["F", "S"]


def test_build_research_context_targets_the_keys():
    ctx = build_research_context([_item("meal_break", "meal_breaks", "state",
                                        cite="Lab 512", heading="Meal periods")])
    assert "meal_break" in ctx and "Lab 512" in ctx and "not yet codified" in ctx


def _cls(id, key, kd=None, authority_state=None, authority_country="US"):
    return {"id": id, "regulation_key": key, "key_definition_id": kd,
            "authority_state": authority_state, "authority_country": authority_country}


def _req(id, key, jur="J", category="minimum_wage", requirement_state=None,
         requirement_country="US"):
    return {"id": id, "regulation_key": key, "jurisdiction_id": jur, "category": category,
            "requirement_state": requirement_state,
            "requirement_country": requirement_country}


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


def test_state_authority_never_codifies_another_jurisdiction():
    # A registry-wide reconcile applies no SQL jurisdiction filter, so the matcher
    # itself must refuse to bind CA authority (Cal. Lab. Code § 510) to the FEDERAL
    # daily_weekly_overtime row — an obligation must not claim authority from a
    # jurisdiction that doesn't govern it. This bound 322 bogus pairs before the guard.
    links = match_codifications(
        [_cls("c_ca", "daily_weekly_overtime", authority_state="CA")],
        [
            _req("r_fed", "daily_weekly_overtime", requirement_state="US"),
            _req("r_ny", "daily_weekly_overtime", requirement_state="NY"),
            _req("r_ca", "daily_weekly_overtime", requirement_state="CA"),
        ],
    )
    assert {l["jurisdiction_requirement_id"] for l in links} == {"r_ca"}


def test_federal_authority_still_binds_every_jurisdiction():
    # A federal/global index has NULL authority_state — federal law applies
    # everywhere, so it keeps binding each jurisdiction's row for that key.
    links = match_codifications(
        [_cls("c_fed", "daily_weekly_overtime", authority_state=None)],
        [
            _req("r_fed", "daily_weekly_overtime", requirement_state="US"),
            _req("r_ca", "daily_weekly_overtime", requirement_state="CA"),
        ],
    )
    assert {l["jurisdiction_requirement_id"] for l in links} == {"r_fed", "r_ca"}


def test_us_federal_authority_never_codifies_a_foreign_row():
    """"Federal law applies everywhere" means everywhere IN THE US.

    Registry keys are a global vocabulary — `national_minimum_wage` is as true of
    the UK as of the US — so key equality alone stamped `29 U.S.C. § 206` (FLSA)
    onto UK and Mexican minimum-wage rows: citing a statute with no force in those
    countries. The state guard could never catch it, because those rows have no
    state. Found by driving a real reconcile against dev data.
    """
    links = match_codifications(
        [_cls("c_flsa", "national_minimum_wage", authority_state=None, authority_country="US")],
        [
            _req("r_us", "national_minimum_wage", requirement_country="US"),
            _req("r_uk", "national_minimum_wage", requirement_country="GB"),
            _req("r_mx", "national_minimum_wage", requirement_country="MX"),
        ],
    )
    assert {l["jurisdiction_requirement_id"] for l in links} == {"r_us"}


def test_country_defaults_to_us_on_both_sides():
    # Legacy rows carry no country_code; the catalog's default is US, so an
    # absent country must not silently drop a legitimate domestic match.
    links = match_codifications(
        [{"id": "c1", "regulation_key": "national_minimum_wage", "key_definition_id": None,
          "authority_state": None}],
        [{"id": "r1", "regulation_key": "national_minimum_wage", "jurisdiction_id": "J",
          "category": "minimum_wage", "requirement_state": None}],
    )
    assert {l["jurisdiction_requirement_id"] for l in links} == {"r1"}


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

def _link(rid, item_id, cite, src="ecfr", level="federal", slug="us-flsa",
          auth_jur=None, auth_state=None, key="exempt_salary_threshold"):
    return {"jurisdiction_requirement_id": rid, "classification_id": "c",
            "item_id": item_id, "citation": cite, "hierarchy": {},
            "index_slug": slug, "source_type": src, "jurisdiction_level": level,
            "authority_jurisdiction_id": auth_jur, "authority_state": auth_state,
            "regulation_key": key}


def _meta(level, state=None, numeric_value=None, current_value=None):
    return {"level": level, "state": state,
            "numeric_value": numeric_value, "current_value": current_value}


def test_stamp_multi_classification_primary_plus_full_set():
    links = [
        _link("r1", "i_usc", "29 U.S.C. § 213"),
        _link("r1", "i_cfr", "29 CFR § 541.600"),
    ]
    stamps, _ = build_citation_stamps(links, {"r1": _meta("federal")})
    assert stamps["r1"]["statute_citation"] == "29 CFR § 541.600"  # regulation wins
    assert stamps["r1"]["citation_item_id"] == "i_cfr"
    cites = [v["citation"] for v in stamps["r1"]["verified_citations"]]
    assert cites == ["29 CFR § 541.600", "29 U.S.C. § 213"]  # sorted, full set


def test_stamp_dedupes_same_item_reached_twice():
    links = [_link("r1", "i_cfr", "29 CFR § 541.600"),
             _link("r1", "i_cfr", "29 CFR § 541.600")]
    stamps, _ = build_citation_stamps(links, {"r1": _meta("federal")})
    assert len(stamps["r1"]["verified_citations"]) == 1


def test_stamp_skips_links_without_item_or_citation():
    links = [{"jurisdiction_requirement_id": "r1", "item_id": None, "citation": None}]
    assert build_citation_stamps(links, {}) == ({}, {})


def test_stamp_state_authority_cannot_cross_state_lines():
    # A California authority must not stamp an Arizona requirement, even though
    # both share the exempt_salary_threshold key (match is jurisdiction-blind).
    links = [_link("r_az", "i_ca", "Cal. Lab. Code § 515",
                   src="curated", level="state", slug="ca-labor-code",
                   auth_jur="CA_ID", auth_state="CA")]
    stamps, baselines = build_citation_stamps(links, {"r_az": _meta("state", state="AZ")})
    assert stamps == {} and baselines == {}  # CA statute rejected for the AZ row


def test_stamp_state_authority_governs_same_state():
    links = [_link("r_ca", "i_ca", "Cal. Lab. Code § 515",
                   src="curated", level="state", slug="ca-labor-code",
                   auth_jur="CA_ID", auth_state="CA")]
    stamps, _ = build_citation_stamps(links, {"r_ca": _meta("state", state="CA")})
    assert stamps["r_ca"]["statute_citation"] == "Cal. Lab. Code § 515"


# ── the jurisdictional split: direct stamp vs floor baseline ────────────────
#
# A federal authority governs every state — but that makes its citation the
# row's OPERATIVE citation only where the state defers to the federal floor.
# TX's exempt threshold is $684/week (the FLSA figure): 29 CFR § 541.600 IS its
# citation. CA's is $70,304/year (CA's own law): stamping the federal reg there
# is false provenance. Both circumstances get stored — direct on
# statute_citation, floor relations in metadata.jurisdictional_basis.

_FED_BASIS = {("exempt_salary_threshold", "federal"):
              {"numeric_value": 684, "current_value": "$684.00/week"}}


def test_state_row_restating_the_federal_floor_gets_the_direct_stamp():
    links = [_link("r_tx", "i_cfr", "29 CFR § 541.600")]
    stamps, baselines = build_citation_stamps(
        links,
        {"r_tx": _meta("state", state="TX", numeric_value=684,
                       current_value="$684.00/week")},
        _FED_BASIS,
    )
    assert stamps["r_tx"]["statute_citation"] == "29 CFR § 541.600"
    assert baselines == {}


def test_state_row_with_its_own_value_gets_a_baseline_not_a_stamp():
    links = [_link("r_ca", "i_cfr", "29 CFR § 541.600")]
    stamps, baselines = build_citation_stamps(
        links,
        {"r_ca": _meta("state", state="CA", numeric_value=70304,
                       current_value="$70,304/year")},
        _FED_BASIS,
    )
    assert "r_ca" not in stamps, "a federal reg must not claim CA's own threshold"
    assert baselines["r_ca"] == [{
        "citation": "29 CFR § 541.600", "item_id": "i_cfr",
        "index_slug": "us-flsa", "level": "federal", "relation": "floor",
    }]


def test_no_basis_value_means_baseline_never_a_guessed_stamp():
    # The federal row for this key isn't codified yet → restatement can't be
    # verified → conservative: record the relation, don't claim the citation.
    links = [_link("r_az", "i_cfr", "29 CFR § 541.600")]
    stamps, baselines = build_citation_stamps(
        links, {"r_az": _meta("state", state="AZ", current_value="$684.00/week")},
    )
    assert "r_az" not in stamps
    assert baselines["r_az"][0]["relation"] == "floor"


def test_value_match_falls_back_to_normalized_text():
    links = [_link("r_nc", "i_cfr", "29 CFR § 541.600")]
    stamps, baselines = build_citation_stamps(
        links,
        {"r_nc": _meta("state", state="NC",
                       current_value="  $684.00/WEEK ")},  # spacing/case noise
        {("exempt_salary_threshold", "federal"):
         {"numeric_value": None, "current_value": "$684.00/week"}},
    )
    assert stamps["r_nc"]["statute_citation"] == "29 CFR § 541.600"
    assert baselines == {}


def test_same_level_stamp_never_needs_a_value_basis():
    # federal authority → federal row: same level, direct regardless of basis.
    links = [_link("r_fed", "i_cfr", "29 CFR § 541.600")]
    stamps, baselines = build_citation_stamps(links, {"r_fed": _meta("federal")})
    assert stamps["r_fed"]["statute_citation"] == "29 CFR § 541.600"
    assert baselines == {}


def test_mixed_direct_and_baseline_on_one_row():
    # A CA row can have a direct CA stamp AND a federal floor baseline.
    links = [
        _link("r_ca", "i_ca", "Cal. Lab. Code § 515", src="curated",
              level="state", slug="ca-labor-code", auth_jur="CA_ID", auth_state="CA"),
        _link("r_ca", "i_cfr", "29 CFR § 541.600"),
    ]
    stamps, baselines = build_citation_stamps(
        links,
        {"r_ca": _meta("state", state="CA", numeric_value=70304)},
        _FED_BASIS,
    )
    assert stamps["r_ca"]["statute_citation"] == "Cal. Lab. Code § 515"
    assert [b["citation"] for b in baselines["r_ca"]] == ["29 CFR § 541.600"]
