"""Unit tests for the Handbook Pilot service — pure corpus + citation gate.

Fast, no DB / no app boot. The citation gate is the security-critical bit:
an unenforceable clause the model tries to ground in a non-existent `law:` ID
must be stripped before the draft reaches the admin.
"""

from app.matcha.services import handbook_pilot as hp


# --- corpus assembly -------------------------------------------------------

def _grounding():
    return {
        "scopes": [{"state": "CA", "city": None, "location_id": None}],
        "profile": {"id": "p", "legal_name": "Acme Inc", "headcount": 40, "hourly_employees": True},
        "requirements": {
            "CA": [
                {"category": "meal_rest_breaks", "title": "Meal and rest breaks",
                 "current_value": "30 min unpaid meal", "jurisdiction_name": "California",
                 "effective_date": "2024-01-01", "description": "Employers must provide..."},
            ],
        },
        "sections": [{"id": "s1", "title": "At-Will Employment", "content": "You are employed at will."}],
        "policies": [{"id": "pol1", "title": "PTO Policy", "category": "hr", "status": "active"}],
        "industry": "hospitality",
    }


def test_build_corpus_flat_index_and_counts():
    corpus = hp.build_corpus(_grounding())
    idx = corpus["index"]
    # index is a flat cid -> record map covering every source record
    total = sum(len(s["records"]) for s in corpus["sources"].values())
    assert len(idx) == total
    # the applicable requirement is minted as a law: record and indexed
    law_cids = [c for c in idx if c.startswith("law:")]
    assert law_cids, "expected at least one law: record"
    assert idx[law_cids[0]]["source"] == "law"
    # profile + existing handbook + existing policy each present
    assert "profile" in idx
    assert any(c.startswith("handbook:") for c in idx)
    assert any(c.startswith("policy:") for c in idx)
    assert any(c.startswith("playbook:") for c in idx)


# --- law cids: content-derived, stable across a jurisdiction-data reorder ----

def _ca(category, title, juris="California", **extra):
    return {"category": category, "title": title, "jurisdiction_name": juris, **extra}


def test_law_cids_are_content_derived_and_stable_under_reordering():
    """The bug this guards: `_fetch_state_requirements` orders by effective /
    updated date, so a jurisdiction data refresh reorders the rows. Positional
    cids re-pointed every stored citation; content-derived cids don't move."""
    reqs = [
        _ca("meal_rest_breaks", "Meal and rest breaks"),
        _ca("paid_sick_leave", "Paid sick leave"),
        _ca("wage_statements", "Wage statement detail"),
    ]
    before = {r["cid"] for r in hp._law_records({"CA": reqs})}
    after = {r["cid"] for r in hp._law_records({"CA": list(reversed(reqs))})}

    assert before == after == {
        "law:ca-meal-rest-breaks-meal-and-rest-breaks",
        "law:ca-paid-sick-leave-paid-sick-leave",
        "law:ca-wage-statements-wage-statement-detail",
    }


def test_law_cid_collisions_qualify_every_member_and_survive_reorder():
    """A state and a city minimum wage share state+category+title. Handing the
    first arrival the bare cid would re-point it on a reorder — every colliding
    member must be qualified by jurisdiction."""
    reqs = [
        _ca("minimum_wage", "Minimum wage", "California", current_value="$16.00"),
        _ca("minimum_wage", "Minimum wage", "San Francisco", current_value="$18.67"),
    ]
    fwd = {r["jurisdiction"]: r["cid"] for r in hp._law_records({"CA": reqs})}
    rev = {r["jurisdiction"]: r["cid"] for r in hp._law_records({"CA": list(reversed(reqs))})}

    assert fwd == rev, "a reorder must not swap which requirement owns which cid"
    assert fwd == {
        "California": "law:ca-minimum-wage-minimum-wage-california",
        "San Francisco": "law:ca-minimum-wage-minimum-wage-san-francisco",
    }


def test_law_cid_identical_rows_get_content_sorted_ordinals():
    """Rows indistinguishable on state/category/title/jurisdiction fall back to
    an ordinal — assigned over a sorted content key, not fetch order."""
    reqs = [
        _ca("minimum_wage", "Minimum wage", "San Francisco", current_value="$18.67"),
        _ca("minimum_wage", "Minimum wage", "San Francisco", current_value="$17.00"),
    ]
    fwd = {r["summary"]: r["cid"] for r in hp._law_records({"CA": reqs})}
    rev = {r["summary"]: r["cid"] for r in hp._law_records({"CA": list(reversed(reqs))})}
    assert fwd == rev
    assert len(set(fwd.values())) == 2, "collisions must not collapse distinct requirements"
    assert all(c.startswith("law:ca-minimum-wage-minimum-wage-san-francisco-") for c in fwd.values())


def test_law_cid_tiebreak_uses_every_field_not_a_subset():
    """Rows tying on the obvious content fields but differing elsewhere must NOT
    fall back to fetch order for their ordinal."""
    reqs = [
        _ca("minimum_wage", "Minimum wage", "San Francisco", source_url="https://a.example.com"),
        _ca("minimum_wage", "Minimum wage", "San Francisco", source_url="https://b.example.com"),
    ]
    fwd = {r["cid"] for r in hp._law_records({"CA": reqs})}
    rev = {r["cid"] for r in hp._law_records({"CA": list(reversed(reqs))})}
    by_url_fwd = {d["source_url"]: r["cid"] for d, r in zip(reqs, hp._law_records({"CA": reqs}))}
    rev_rows = list(reversed(reqs))
    by_url_rev = {d["source_url"]: r["cid"] for d, r in zip(rev_rows, hp._law_records({"CA": rev_rows}))}
    assert fwd == rev
    assert by_url_fwd == by_url_rev, "a reorder must not swap which row owns which ordinal"


def test_law_cid_cross_group_collision_keeps_both_requirements():
    """A jurisdiction-qualified cid from one collision group can equal a bare cid
    from another. build_corpus keys the index by cid — neither may be dropped."""
    reqs = [
        _ca("minimum_wage", "Minimum wage", "California"),
        _ca("minimum_wage", "Minimum wage", "San Francisco"),
        _ca("minimum_wage", "Minimum wage San Francisco", "California"),
    ]
    recs = hp._law_records({"CA": reqs})
    cids = [r["cid"] for r in recs]
    assert len(set(cids)) == 3, f"cid collision dropped a requirement: {cids}"

    idx = hp.build_corpus({"requirements": {"CA": reqs}})["index"]
    assert len([c for c in idx if c.startswith("law:")]) == 3


def test_law_records_carry_structured_fields():
    r = hp._law_records(_grounding()["requirements"])[0]
    assert r["state"] == "CA"
    assert r["title"] == "Meal and rest breaks"
    assert r["category"] == "meal_rest_breaks"
    assert r["jurisdiction"] == "California"


# --- legacy positional citations: prefix recovery ---------------------------

def test_legacy_cid_resolves_by_state_category_prefix():
    """A citation stored as `law:ca-meal-rest-breaks-0` names a category that now
    has exactly one requirement — honor it, whatever ordinal it was written as."""
    corpus = hp.build_corpus(_grounding())
    idx = corpus["index"]
    canon = "law:ca-meal-rest-breaks-meal-and-rest-breaks"

    for legacy in ("law:ca-meal-rest-breaks-0", "law:ca-meal-rest-breaks-7"):
        resolved = hp.resolve_citations([legacy], idx)[0]
        assert resolved["source"] == "law"
        assert resolved["cid"] == canon, "displayed under the canonical cid"
        assert hp.canonical_cid(legacy, idx) == canon


def test_legacy_cid_refuses_to_guess_when_prefix_is_ambiguous():
    """Two minimum wages under one category: the ordinal was the only thing that
    distinguished them, and it's exactly what moved. Flag it, don't guess."""
    g = _grounding()
    g["requirements"]["CA"] = [
        _ca("minimum_wage", "Minimum wage", "California"),
        _ca("minimum_wage", "Minimum wage", "San Francisco"),
    ]
    idx = hp.build_corpus(g)["index"]
    assert hp.lookup_record("law:ca-minimum-wage-0", idx) is None
    resolved = hp.resolve_citations(["law:ca-minimum-wage-0"], idx)[0]
    assert resolved["source"] == "unknown"
    assert resolved["source_label"] == "No longer in scope"


def test_lookup_record_rejects_non_law_and_garbage():
    idx = hp.build_corpus(_grounding())["index"]
    assert hp.lookup_record("handbook:ghost-1", idx) is None  # ordinal-looking, not law:
    assert hp.lookup_record("law:zz-nothing-0", idx) is None
    assert hp.lookup_record(None, idx) is None
    assert hp.canonical_cid("law:zz-nothing-0", idx) == "law:zz-nothing-0"


def test_legacy_recovery_does_not_bleed_across_category_boundaries():
    """`paid-leave` is a string prefix of `paid-leave-and-sick-time`. Recovery
    compares the structured state+category, so the old citation stays unresolved
    rather than silently naming a different category's requirement."""
    g = _grounding()
    g["requirements"]["CA"] = [_ca("paid_leave_and_sick_time", "Combined leave")]
    idx = hp.build_corpus(g)["index"]
    assert hp.lookup_record("law:ca-paid-leave-0", idx) is None
    # the requirement's OWN legacy prefix still resolves
    assert hp.canonical_cid("law:ca-paid-leave-and-sick-time-0", idx) \
        == "law:ca-paid-leave-and-sick-time-combined-leave"


def test_legacy_recovery_ignores_current_cids_whose_title_ends_in_digits():
    """`law:ca-osha-recordkeeping-osha-form-300` is a CURRENT cid, not a legacy
    positional one. If it ages out of scope it must be flagged, never re-pointed
    at the sibling Form 300A requirement."""
    g = _grounding()
    g["requirements"]["CA"] = [_ca("osha_recordkeeping", "OSHA Form 300A")]
    idx = hp.build_corpus(g)["index"]
    aged_out = "law:ca-osha-recordkeeping-osha-form-300"
    assert hp.lookup_record(aged_out, idx) is None
    resolved = hp.resolve_citations([aged_out], idx)[0]
    assert resolved["source"] == "unknown"
    assert resolved["source_label"] == "No longer in scope"


def test_coerce_drafts_gate_is_exact_match_and_never_launders_invented_cids():
    """The citation gate must not run model output through legacy recovery: an
    invented `law:ca-<category>-<n>` would otherwise resolve to the one real
    requirement in that category instead of being dropped."""
    g = _grounding()
    g["requirements"]["CA"] = [_ca("overtime", "Overtime pay")]
    idx = hp.build_corpus(g)["index"]
    canon = "law:ca-overtime-overtime-pay"
    raw = [{"kind": "handbook_section", "title": "Overtime", "content": "body",
            "cited_ids": [canon, canon, "law:ca-overtime-2025", "law:ghost-99"]}]
    drafts, dropped = hp._coerce_drafts(raw, idx)
    assert dropped == ["law:ca-overtime-2025", "law:ghost-99"]
    assert drafts[0]["cited_ids"] == [canon]  # deduped, nothing laundered


def test_resolve_citations_dedupes_by_resolved_cid():
    """Two legacy cids under one state+category collapse onto the same record —
    the viewer keys its citation cards on cid, so don't emit it twice."""
    idx = hp.build_corpus(_grounding())["index"]
    canon = "law:ca-meal-rest-breaks-meal-and-rest-breaks"
    resolved = hp.resolve_citations(
        ["law:ca-meal-rest-breaks-3", "law:ca-meal-rest-breaks-7", canon], idx)
    assert [c["cid"] for c in resolved] == [canon]


def test_build_corpus_notes_when_no_scopes():
    g = _grounding()
    g["scopes"] = []
    g["requirements"] = {}
    corpus = hp.build_corpus(g)
    assert corpus["notes"], "expected a note when no work locations are on file"


def test_build_corpus_tolerates_empty_grounding():
    """No profile, no locations, no existing content — build a corpus anyway.

    The index is NOT empty: `_playbook_records` falls back to the `general`
    industry, which carries a summary and baseline sections, and those are real
    citable records independent of tenant data. What must be empty is everything
    DERIVED from the (absent) company data — and the notes must say why."""
    corpus = hp.build_corpus({})
    assert isinstance(corpus["sources"], dict)

    for key in ("profile", "law", "existing_handbook", "existing_policies", "compliance_floor"):
        assert corpus["sources"][key]["records"] == [], key
    playbook = corpus["sources"]["playbook"]["records"]
    assert playbook, "the industry baseline grounds a session with no data of its own"
    assert all(r["cid"].startswith("playbook:") for r in playbook)

    # flat-index invariant holds over whatever WAS minted
    assert set(corpus["index"]) == {r["cid"] for r in playbook}
    assert all(corpus["index"][r["cid"]]["source"] == "playbook" for r in playbook)

    # absence is stated, never silent
    assert any("No work locations on file" in n for n in corpus["notes"])
    assert any("No jurisdiction requirements" in n for n in corpus["notes"])


# --- draft coercion + citation gate ----------------------------------------

def test_coerce_drafts_drops_hallucinated_citations():
    index = {"law:ca-meal-0": {}, "policy:pol1": {}}
    raw = [{
        "kind": "handbook_section", "title": "Meal & Rest Breaks",
        "content": "Employees receive a 30-minute unpaid meal period.",
        "cited_ids": ["law:ca-meal-0", "law:ghost-99"],
    }]
    drafts, dropped = hp._coerce_drafts(raw, index)
    assert dropped == ["law:ghost-99"]
    assert len(drafts) == 1
    assert drafts[0]["cited_ids"] == ["law:ca-meal-0"]
    # section_key derived from the title when absent
    assert drafts[0]["section_key"] == "meal-rest-breaks"


def test_coerce_drafts_coerces_bad_kind_and_skips_empty():
    index = {}
    raw = [
        {"kind": "nonsense", "title": "T", "content": "body", "cited_ids": []},
        {"kind": "policy", "title": "", "content": "no title", "cited_ids": []},  # skipped
        {"kind": "policy", "title": "Has title", "content": "", "cited_ids": []},  # skipped
    ]
    drafts, _ = hp._coerce_drafts(raw, index)
    assert len(drafts) == 1
    assert drafts[0]["kind"] == "handbook_section"  # bad kind coerced


def test_coerce_drafts_caps_count():
    index = {}
    raw = [{"kind": "policy", "title": f"P{i}", "content": "x", "cited_ids": []}
           for i in range(20)]
    drafts, _ = hp._coerce_drafts(raw, index)
    assert len(drafts) <= hp._MAX_DRAFTS_PER_TURN


def test_coerce_drafts_tolerates_garbage():
    drafts, dropped = hp._coerce_drafts("not-a-list", {})
    assert drafts == [] and dropped == []
    drafts, _ = hp._coerce_drafts([None, "x", 3], {})
    assert drafts == []


# --- inline corpus-id stripping --------------------------------------------

def test_strip_corpus_citations_removes_all_cid_forms():
    text = ("Accrue leave [law:ca-sick-accrual] and report concerns "
            "[handbook:0e297b8f-58e6-4e21-9b6e-b6d4f98ee87c]; see [policy:pol1], "
            "the [playbook:tips] baseline, and [profile].")
    clean, found = hp.strip_corpus_citations(text)
    assert "[law:" not in clean and "[handbook:" not in clean
    assert "[policy:" not in clean and "[playbook:" not in clean and "[profile]" not in clean
    assert found == ["law:ca-sick-accrual",
                     "handbook:0e297b8f-58e6-4e21-9b6e-b6d4f98ee87c",
                     "policy:pol1", "playbook:tips", "profile"]
    # preceding space is consumed with the tag; no double spaces or space-before-punct
    assert clean == "Accrue leave and report concerns; see, the baseline, and."


def test_strip_corpus_citations_preserves_placeholders_and_links():
    text = "Email [HR_CONTACT_EMAIL] or read our [handbook policy](https://x.test/p)."
    clean, found = hp.strip_corpus_citations(text)
    assert clean == text          # nothing stripped
    assert found == []


def test_strip_corpus_citations_leaves_bare_prose_untouched():
    clean, found = hp.strip_corpus_citations("Just plain handbook text, no tags.")
    assert found == [] and clean == "Just plain handbook text, no tags."


def test_coerce_drafts_strips_inline_tags_and_harvests_valid_ids():
    """A model that only tagged inline (empty cited_ids) still ends grounded:
    real inline ids are harvested into cited_ids, the prose comes out clean, and
    an invented inline id is stripped from prose AND reported as dropped."""
    index = {"law:ca-meal-0": {}, "handbook:h1": {}}
    raw = [{
        "kind": "handbook_section", "title": "Meal & Rest Breaks",
        "content": ("Employees receive a 30-minute unpaid meal period "
                    "[law:ca-meal-0], building on [handbook:h1] "
                    "and [law:invented-99]. Contact [HR_CONTACT_EMAIL]."),
        "cited_ids": [],
    }]
    drafts, dropped = hp._coerce_drafts(raw, index)
    assert len(drafts) == 1
    c = drafts[0]["content"]
    assert "[law:" not in c and "[handbook:" not in c
    assert "[HR_CONTACT_EMAIL]" in c                 # placeholder preserved
    assert drafts[0]["cited_ids"] == ["law:ca-meal-0", "handbook:h1"]  # harvested
    assert dropped == ["law:invented-99"]


def test_coerce_drafts_unions_field_and_inline_without_dupes():
    index = {"law:ca-meal-0": {}}
    raw = [{
        "kind": "policy", "title": "Meal", "content": "Body [law:ca-meal-0].",
        "cited_ids": ["law:ca-meal-0"],
    }]
    drafts, _ = hp._coerce_drafts(raw, index)
    assert drafts[0]["cited_ids"] == ["law:ca-meal-0"]  # not duplicated
    assert drafts[0]["content"] == "Body."


def test_assemble_handbook_strips_inline_tags_from_legacy_content():
    """Read path cleans drafts stored before the fix — no backfill needed."""
    drafts = [{"id": "d1", "kind": "handbook_section", "title": "T",
               "content": "Report to [handbook:old] as needed.",
               "status": "pending", "citations": [], "promoted_ref": None}]
    asm = hp.assemble_handbook({}, drafts, hp.build_corpus({}))
    assert asm["sections"][0]["content"] == "Report to as needed."


# --- handbook viewer: citation resolution ----------------------------------

def _index():
    return {
        "law:ca-meal-0": {"ref": "CA · California: Meal breaks", "summary": "30 min unpaid",
                          "source": "law", "source_label": "Applicable jurisdiction requirements",
                          "when": "2024-01-01"},
        "playbook:tips": {"ref": "Playbook — Tips", "summary": "tip pooling",
                          "source": "playbook", "source_label": "Industry playbook baseline",
                          "when": "baseline"},
    }


def test_resolve_citations_maps_known_and_flags_unknown():
    resolved = hp.resolve_citations(["law:ca-meal-0", "law:ghost-9", "playbook:tips"], _index())
    assert resolved[0]["source"] == "law" and resolved[0]["ref"].startswith("CA")
    # a cid that aged out of scope resolves to a clearly-flagged stub, not dropped
    assert resolved[1]["cid"] == "law:ghost-9"
    assert resolved[1]["source"] == "unknown"
    assert resolved[1]["source_label"] == "No longer in scope"
    assert resolved[2]["source"] == "playbook"


def test_resolve_citations_tolerates_string_and_garbage():
    # drafts loaded via the route arrive parsed, but a JSON-string is accepted too
    assert hp.resolve_citations('["law:ca-meal-0"]', _index())[0]["cid"] == "law:ca-meal-0"
    assert hp.resolve_citations(None, _index()) == []
    assert hp.resolve_citations([1, 2, None], _index()) == []


# --- handbook viewer: document assembly + coverage -------------------------

def _drafts():
    return [
        {"id": "d1", "kind": "handbook_section", "title": "Meal & Rest", "section_key": "meal_rest",
         "content": "body A", "status": "pending", "promoted_ref": None, "citations": ["law:ca-meal-0"]},
        {"id": "d2", "kind": "handbook_section", "title": "Intro", "section_key": "intro",
         "content": "welcome", "status": "promoted",
         "promoted_ref": {"kind": "handbook", "handbook_id": "HB1"}, "citations": []},
        {"id": "d3", "kind": "policy", "title": "Tips Policy", "section_key": "tips",
         "content": "tips body", "status": "pending", "promoted_ref": None, "citations": ["playbook:tips"]},
    ]


def _corpus():
    idx = dict(_index())
    idx["law:ca-meal-0"] = {**idx["law:ca-meal-0"], "state": "CA", "title": "Meal breaks",
                            "category": "meal_rest_breaks", "jurisdiction": "California"}
    # a second law record nobody cites → an uncovered / candidate-gap requirement
    idx["law:ca-osha-1"] = {"ref": "CA OSHA log", "summary": "",
                            "source": "law", "source_label": "Applicable jurisdiction requirements",
                            "state": "CA", "title": "OSHA log", "category": "osha",
                            "jurisdiction": "California"}
    return {"index": idx}


def test_assemble_handbook_splits_sections_and_policies_in_order():
    asm = hp.assemble_handbook({"title": "S"}, _drafts(), _corpus())
    assert [s["id"] for s in asm["sections"]] == ["d1", "d2"]  # input (created_at) order preserved
    assert [p["id"] for p in asm["policies"]] == ["d3"]
    assert asm["summary"]["section_count"] == 2
    assert asm["summary"]["policy_count"] == 1


def test_assemble_handbook_grounded_flag_and_promoted_ref():
    asm = hp.assemble_handbook({}, _drafts(), _corpus())
    meal, intro = asm["sections"]
    assert meal["grounded"] is True and meal["law_citation_count"] == 1
    assert meal["citations"][0]["ref"].startswith("CA")
    assert intro["grounded"] is False
    assert intro["promoted_ref"]["handbook_id"] == "HB1"
    assert asm["summary"]["grounded_sections"] == 1


def test_assemble_handbook_coverage_covered_vs_uncovered():
    asm = hp.assemble_handbook({}, _drafts(), _corpus())
    cov = asm["coverage"]
    # 2 law records in the corpus; ca-meal-0 is cited, ca-osha-1 is not
    assert asm["summary"]["law_records"] == 2
    assert [c["cid"] for c in cov["covered"]] == ["law:ca-meal-0"]
    assert [c["cid"] for c in cov["uncovered"]] == ["law:ca-osha-1"]
    assert asm["summary"]["covered"] == 1 and asm["summary"]["uncovered"] == 1
    # entries carry the fields the viewer groups + joins on, and who cites them
    assert cov["covered"][0]["state"] == "CA"
    assert cov["covered"][0]["title"] == "Meal breaks"
    assert cov["covered"][0]["cited_by"] == ["d1"]
    assert cov["uncovered"][0]["cited_by"] == []


def test_assemble_handbook_coverage_counts_legacy_citation_once():
    """A draft written before the cid change cites the positional id. It must
    still count as covering the requirement — once, under the canonical cid."""
    corpus = hp.build_corpus(_grounding())
    canon = "law:ca-meal-rest-breaks-meal-and-rest-breaks"
    drafts = [{"id": "old", "kind": "handbook_section", "title": "Meal & Rest",
               "section_key": "meal_rest", "content": "body", "status": "pending",
               "promoted_ref": None, "citations": ["law:ca-meal-rest-breaks-0", canon]}]

    asm = hp.assemble_handbook({}, drafts, corpus)
    assert asm["summary"]["law_records"] == 1
    assert asm["summary"]["covered"] == 1 and asm["summary"]["uncovered"] == 0
    assert [c["cid"] for c in asm["coverage"]["covered"]] == [canon]
    assert asm["coverage"]["covered"][0]["cited_by"] == ["old"]  # not ["old", "old"]


def test_assemble_handbook_tolerates_empty():
    asm = hp.assemble_handbook({}, [], {})
    assert asm["summary"]["section_count"] == 0
    assert asm["coverage"]["covered"] == [] and asm["coverage"]["uncovered"] == []


# --- compliance scan: pure helpers -----------------------------------------

def test_sort_gaps_by_severity():
    gaps = [{"severity": "recommended", "requirement_title": "B"},
            {"severity": "critical", "requirement_title": "A"},
            {"severity": "important", "requirement_title": "C"}]
    assert [g["requirement_title"] for g in hp._sort_gaps_by_severity(gaps)] == ["A", "C", "B"]


def test_dedupe_matched_keeps_first_per_key():
    matched = hp._dedupe_matched("CA", [
        {"covered": True, "requirement_key": "k1", "requirement_title": "T1", "matched_section_title": "Sec1"},
        {"covered": True, "requirement_key": "k1", "requirement_title": "T1 dup"},
        {"covered": False, "requirement_key": "k2"},
    ])
    assert len(matched) == 1
    assert matched[0]["state"] == "CA" and matched[0]["matched_section_title"] == "Sec1"


# --- compliance floor (C1) ----------------------------------------------------

def _chain(location_label="Main Office", category="meal_rest_breaks"):
    """Shape of one `matcha_work_node.build_compliance_context` reasoning chain."""
    return {
        "location_id": "loc-1",
        "location_label": location_label,
        "categories": [{
            "category": category,
            "governing_level": "state",
            "precedence_type": "floor",
            "legal_citation": "Cal. Lab. Code § 512",
            "reasoning_text": "State floor exceeds the federal baseline.",
            "all_levels": [
                {"jurisdiction_level": "federal", "jurisdiction_name": "Federal",
                 "title": "No federal meal requirement", "is_governing": False},
                {"jurisdiction_level": "state", "jurisdiction_name": "California",
                 "title": "Meal and rest breaks", "current_value": "30 min unpaid after 5 hrs",
                 "is_governing": True, "statute_citation": "Cal. Lab. Code § 512",
                 "effective_date": "2024-01-01"},
            ],
        }],
    }


def test_corpus_carries_the_governing_floor_alongside_the_flat_law_list():
    corpus = hp.build_corpus({**_grounding(), "reasoning_chains": [_chain()]})
    floor = [c for c in corpus["index"] if c.startswith("floor:")]
    assert floor, "expected a floor: record"
    assert corpus["index"][floor[0]]["source"] == "compliance_floor"
    # the flat per-state list is still there — the floor supplements it
    assert any(c.startswith("law:") for c in corpus["index"])
    assert not any("No precedence-resolved compliance floor" in n for n in corpus["notes"])


def test_no_chains_says_so_rather_than_reading_as_resolved():
    corpus = hp.build_corpus(_grounding())
    assert corpus["sources"]["compliance_floor"]["records"] == []
    assert any("No precedence-resolved compliance floor" in n for n in corpus["notes"])


def test_floor_records_dedupe_across_locations():
    # same state rule reached from three offices = one citable record naming all
    corpus = hp.build_corpus({"reasoning_chains": [
        _chain("Main Office"), _chain("Warehouse"), _chain("Satellite")]})
    recs = corpus["sources"]["compliance_floor"]["records"]
    assert len(recs) == 1
    assert recs[0]["applies_to"] == ["Main Office", "Warehouse", "Satellite"]


def test_hr_pilot_corpus_mints_the_floor_exactly_once():
    """`build_hr_pilot_corpus` delegates the shared groups to `build_corpus`,
    which now owns compliance_floor. Minting it again there would render every
    floor record twice in the prompt (the index dedupes on cid; the prompt does
    not) and state the no-floor note twice."""
    from app.matcha.services.hr_pilot_corpus import build_hr_pilot_corpus

    corpus = build_hr_pilot_corpus(_grounding(), [_chain()])
    groups = [k for k in corpus["sources"] if k == "compliance_floor"]
    assert groups == ["compliance_floor"]
    assert len(corpus["sources"]["compliance_floor"]["records"]) == 1

    empty = build_hr_pilot_corpus(_grounding(), [])
    notes = [n for n in empty["notes"] if "No precedence-resolved compliance floor" in n]
    assert len(notes) == 1


def test_hr_pilot_corpus_still_accepts_chains_only_via_the_parameter():
    """Back-compat: the caller in matcha_work_mode_contexts passes chains as a
    positional argument, not inside grounding."""
    from app.matcha.services.hr_pilot_corpus import build_hr_pilot_corpus

    corpus = build_hr_pilot_corpus({"scopes": [], "industry": "general"}, [_chain()])
    assert corpus["sources"]["compliance_floor"]["records"]


# --- full-text drafting (C2) --------------------------------------------------

def test_full_text_map_caps_each_record_and_marks_the_truncation():
    long_body = "x" * (hp._FULL_TEXT_PER_RECORD + 500)
    grounding = {"sections": [{"id": "s1", "content": long_body}],
                 "policies": [{"id": "pol1", "content": "short policy body"}]}
    full_text, overflow = hp._full_text_map(grounding)
    assert overflow == 0
    assert full_text["policy:pol1"] == "short policy body"
    assert full_text["handbook:s1"].startswith("x" * 100)
    assert "(body truncated)" in full_text["handbook:s1"]
    assert len(full_text["handbook:s1"]) <= hp._FULL_TEXT_PER_RECORD + 40


def test_full_text_budget_overflows_to_summaries_with_a_note():
    body = "y" * hp._FULL_TEXT_PER_RECORD
    n = hp._FULL_TEXT_BUDGET // hp._FULL_TEXT_PER_RECORD + 3
    grounding = {**_grounding(),
                 "sections": [{"id": f"s{i}", "title": f"S{i}", "content": body}
                              for i in range(n)],
                 "policies": []}
    corpus = hp.build_corpus(grounding, with_full_text=True)
    assert len(corpus["full_text"]) < n                      # overflow dropped
    assert any("full-text budget" in note for note in corpus["notes"])
    # every section is still CITABLE — only its body fell back to the summary
    assert all(f"handbook:s{i}" in corpus["index"] for i in range(n))


def test_prompt_renders_full_bodies_and_falls_back_to_summaries():
    grounding = {**_grounding(),
                 "sections": [{"id": "s1", "title": "Attendance",
                               "content": "Full attendance policy body. " * 20}],
                 "policies": [{"id": "pol1", "title": "PTO Policy", "category": "hr",
                               "status": "active", "content": "PTO accrues at 1.5 days/month."}]}
    corpus = hp.build_corpus(grounding, with_full_text=True)
    text = hp._corpus_text(corpus)
    assert "PTO accrues at 1.5 days/month." in text          # policy body, absent before
    assert "Full attendance policy body." in text
    # a record with no body still renders its index summary
    assert "Acme Inc" in text


def test_full_text_is_not_folded_into_the_stored_records():
    """Records ride in message/draft metadata — they stay index-sized."""
    grounding = {**_grounding(),
                 "sections": [{"id": "s1", "title": "Attendance", "content": "z" * 5_000}]}
    corpus = hp.build_corpus(grounding, with_full_text=True)
    rec = corpus["index"]["handbook:s1"]
    assert len(rec["summary"]) <= 290
    assert "full_text" not in rec


# --- floor citations count as legal grounding ---------------------------------

def _floor_index(category="meal_rest_breaks", level="state", juris="California"):
    return {
        "cid": f"floor:{level}-{juris.lower()}-{category}",
        "ref": f"{level} · {juris}: Meal and rest breaks",
        "summary": "Meal and rest breaks — requirement: 30 min unpaid.",
        "source": "compliance_floor", "source_label": "Governing compliance requirements",
        "category": category, "governing_level": level, "jurisdiction": juris,
    }


def test_a_draft_citing_only_the_floor_still_reads_as_grounded():
    """The drafting prompt tells the model to prefer the governing `floor:`
    record over the flat `law:` list — counting only `law:` would mark exactly
    the best-grounded drafts ungrounded."""
    floor = _floor_index()
    corpus = {"index": {**_corpus()["index"], floor["cid"]: floor}}
    drafts = [{"id": "d1", "kind": "handbook_section", "title": "Meal & Rest",
               "section_key": "meal_rest", "content": "body", "status": "pending",
               "promoted_ref": None, "citations": [floor["cid"]]}]
    asm = hp.assemble_handbook({}, drafts, corpus)
    assert asm["sections"][0]["grounded"] is True
    assert asm["sections"][0]["law_citation_count"] == 1


def test_floor_citation_covers_the_flat_requirement_for_the_same_category():
    floor = _floor_index()
    corpus = {"index": {**_corpus()["index"], floor["cid"]: floor}}
    drafts = [{"id": "d1", "kind": "handbook_section", "title": "Meal & Rest",
               "section_key": "meal_rest", "content": "body", "status": "pending",
               "promoted_ref": None, "citations": [floor["cid"]]}]
    asm = hp.assemble_handbook({}, drafts, corpus)
    covered = {c["cid"]: c for c in asm["coverage"]["covered"]}
    uncovered = {u["cid"] for u in asm["coverage"]["uncovered"]}
    assert "law:ca-meal-0" in covered              # matched through the floor
    assert covered["law:ca-meal-0"]["cited_by"] == ["d1"]
    assert "law:ca-osha-1" in uncovered            # different category — still a gap


def test_a_floor_from_another_state_does_not_cover_this_states_requirement():
    floor = _floor_index(juris="Texas")
    corpus = {"index": {**_corpus()["index"], floor["cid"]: floor}}
    drafts = [{"id": "d1", "kind": "handbook_section", "title": "Meal & Rest",
               "section_key": "meal_rest", "content": "body", "status": "pending",
               "promoted_ref": None, "citations": [floor["cid"]]}]
    asm = hp.assemble_handbook({}, drafts, corpus)
    assert "law:ca-meal-0" in {u["cid"] for u in asm["coverage"]["uncovered"]}


def test_a_federal_floor_covers_the_category_in_every_state():
    floor = _floor_index(level="federal", juris="Federal")
    corpus = {"index": {**_corpus()["index"], floor["cid"]: floor}}
    drafts = [{"id": "d1", "kind": "handbook_section", "title": "Meal & Rest",
               "section_key": "meal_rest", "content": "body", "status": "pending",
               "promoted_ref": None, "citations": [floor["cid"]]}]
    asm = hp.assemble_handbook({}, drafts, corpus)
    assert "law:ca-meal-0" in {c["cid"] for c in asm["coverage"]["covered"]}


# --- review fixes -------------------------------------------------------------

def test_gather_grounding_does_not_fetch_the_floor_itself():
    """`build_compliance_context` opens its own pooled connection, so fetching it
    while the route still holds one nests two acquisitions out of a pool of ten.
    The chains arrive via `attach_compliance_floor`, called after the block."""
    import inspect
    src = inspect.getsource(hp.gather_grounding)
    assert "build_compliance_context" not in src
    assert "reasoning_chains" in inspect.getsource(hp.attach_compliance_floor)


def test_attach_compliance_floor_degrades_to_empty(monkeypatch):
    import asyncio

    class _Boom:
        async def build_compliance_context(self, company_id):
            raise RuntimeError("compliance service down")

    monkeypatch.setitem(__import__("sys").modules,
                        "app.matcha.services.matcha_work_node", _Boom())
    g = asyncio.run(hp.attach_compliance_floor({"scopes": []}, "cid"))
    assert g["reasoning_chains"] == []


def test_full_text_is_opt_in_so_hr_pilots_cached_corpus_stays_small():
    """`build_hr_pilot_corpus` delegates here and its result is Redis-cached per
    company; an unconditional map would store up to 120k chars HR never reads."""
    from app.matcha.services.hr_pilot_corpus import build_hr_pilot_corpus

    grounding = {**_grounding(),
                 "sections": [{"id": "s1", "title": "T", "content": "x" * 5_000}]}
    assert hp.build_corpus(grounding)["full_text"] == {}
    assert hp.build_corpus(grounding, with_full_text=True)["full_text"]

    # HR Pilot's corpus doesn't carry the key at all — it builds its own
    # full-text map at prompt time (matcha_work_mode_contexts).
    assert not build_hr_pilot_corpus(grounding, []).get("full_text")


def test_a_federal_floor_does_not_cover_a_state_with_its_own_governing_floor():
    """CA and TX locations: federal governs the category in TX while California
    governs it in CA. Citing the federal floor must not mark CA's requirement
    covered — the draft states the weaker federal rule for CA employees."""
    federal = _floor_index(level="federal", juris="Federal")
    california = _floor_index(level="state", juris="California")
    corpus = {"index": {**_corpus()["index"],
                        federal["cid"]: federal, california["cid"]: california}}
    drafts = [{"id": "d1", "kind": "handbook_section", "title": "Meal & Rest",
               "section_key": "meal_rest", "content": "body", "status": "pending",
               "promoted_ref": None, "citations": [federal["cid"]]}]
    asm = hp.assemble_handbook({}, drafts, corpus)
    assert "law:ca-meal-0" in {u["cid"] for u in asm["coverage"]["uncovered"]}

    # citing California's own floor does cover it
    drafts[0]["citations"] = [california["cid"]]
    asm = hp.assemble_handbook({}, drafts, corpus)
    assert "law:ca-meal-0" in {c["cid"] for c in asm["coverage"]["covered"]}


def test_a_federal_floor_still_covers_a_state_with_no_local_floor():
    federal = _floor_index(level="federal", juris="Federal")
    corpus = {"index": {**_corpus()["index"], federal["cid"]: federal}}
    drafts = [{"id": "d1", "kind": "handbook_section", "title": "Meal & Rest",
               "section_key": "meal_rest", "content": "body", "status": "pending",
               "promoted_ref": None, "citations": [federal["cid"]]}]
    asm = hp.assemble_handbook({}, drafts, corpus)
    assert "law:ca-meal-0" in {c["cid"] for c in asm["coverage"]["covered"]}


# --- audit gaps + freshness findings (C3) -------------------------------------

def _audit(days_ago: int = 10, n_extra: int = 0):
    from datetime import datetime, timedelta, timezone
    gaps = [
        {"state": "CA", "requirement_key": "paid_sick_leave",
         "requirement_title": "Paid sick leave accrual", "covered": False,
         "severity": "critical", "citation": "Cal. Lab. Code § 246",
         "what_good_looks_like": "State the accrual rate and carryover cap.",
         "matched_section_title": "Time Off"},
        {"state": "CA", "requirement_key": "lactation_accommodation",
         "requirement_title": "Lactation accommodation", "covered": False,
         "severity": "recommended", "what_good_looks_like": "Name the private space."},
        # already covered by the handbook — must never become a record
        {"state": "CA", "requirement_key": "at_will", "requirement_title": "At-will notice",
         "covered": True, "severity": "critical"},
    ]
    gaps += [{"state": "TX", "requirement_key": f"extra_{i}",
              "requirement_title": f"Extra requirement {i}", "covered": False,
              "severity": "recommended"} for i in range(n_extra)]
    return {"report_id": "r1", "states": ["CA"], "industry": "hospitality",
            "completed_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
            "gaps": gaps}


def _freshness(n: int = 2, change_request: bool = False):
    from datetime import datetime, timezone
    return [{"id": f"f{i}", "section_key": f"section_{i}", "finding_type": "outdated",
             "summary": f"Finding {i}: the meal-break rule changed.",
             "source_url": "https://example.com/law", "effective_date": "2026-01-01",
             "age_days": 400, "change_request_id": ("cr1" if change_request else None),
             "checked_at": datetime.now(timezone.utc), "handbook_title": "US Handbook"}
            for i in range(n)]


def test_audit_records_only_uncovered_gaps_severity_first():
    recs, notes = hp._audit_records(_audit())
    cids = [r["cid"] for r in recs]
    assert cids == ["audit:ca-paid-sick-leave", "audit:ca-lactation-accommodation"]
    assert not any("at-will" in c for c in cids)   # covered gaps are not findings
    assert notes == []                             # fresh audit, nothing truncated

    top = recs[0]
    assert "critical gap" in top["summary"] and "Paid sick leave accrual" in top["summary"]
    assert "what good looks like" in top["summary"]
    assert "Cal. Lab. Code § 246" in top["summary"]
    assert "Time Off" in top["summary"]            # closest existing section named


def test_audit_records_cap_and_stale_notes():
    recs, notes = hp._audit_records(_audit(days_ago=400, n_extra=hp._MAX_AUDIT_GAPS + 10))
    assert len(recs) == hp._MAX_AUDIT_GAPS
    # the criticals survive the cut — ranking happens before the cap
    assert recs[0]["cid"] == "audit:ca-paid-sick-leave"
    assert any("400 days ago" in n for n in notes)
    assert any(str(hp._MAX_AUDIT_GAPS) in n for n in notes)


def test_audit_records_empty_and_junk():
    assert hp._audit_records(None) == ([], [])
    assert hp._audit_records({}) == ([], [])
    assert hp._audit_records({"gaps": ["junk", None, 3]}) == ([], [])
    # every gap already covered → no records, no note
    assert hp._audit_records({"gaps": [{"covered": True, "requirement_title": "x"}]}) == ([], [])


def test_audit_cids_are_unique_when_two_gaps_share_a_key():
    dup = {"gaps": [{"state": "CA", "requirement_key": "wage", "requirement_title": "Wage A"},
                    {"state": "CA", "requirement_key": "wage", "requirement_title": "Wage B"}]}
    recs, _ = hp._audit_records(dup)
    assert [r["cid"] for r in recs] == ["audit:ca-wage", "audit:ca-wage-2"]


def test_freshness_records_and_change_request_flag():
    recs, notes = hp._freshness_records(_freshness())
    assert [r["cid"] for r in recs] == ["fresh:f0", "fresh:f1"]
    assert notes == []
    s = recs[0]["summary"]
    assert "US Handbook" in s and "section_0" in s
    assert "law this section relies on has changed" in s
    assert "effective 2026-01-01" in s
    assert "already been raised" not in s

    withcr, _ = hp._freshness_records(_freshness(n=1, change_request=True))
    assert "already been raised" in withcr[0]["summary"]


def test_freshness_records_cap_notes_and_empties():
    recs, notes = hp._freshness_records(_freshness(n=hp._MAX_FRESHNESS_FINDINGS + 5))
    assert len(recs) == hp._MAX_FRESHNESS_FINDINGS
    assert any(str(hp._MAX_FRESHNESS_FINDINGS) in n for n in notes)
    assert hp._freshness_records(None) == ([], [])
    assert hp._freshness_records([]) == ([], [])


def test_build_corpus_indexes_audit_and_freshness():
    corpus = hp.build_corpus({**_grounding(), "audit": _audit(), "freshness": _freshness()})
    idx = corpus["index"]
    assert idx["audit:ca-paid-sick-leave"]["source"] == "handbook_audit"
    assert idx["fresh:f0"]["source"] == "handbook_freshness"
    # still one flat index — every record reachable by the citation gate
    assert len(idx) == sum(len(s["records"]) for s in corpus["sources"].values())


def test_a_finding_is_not_legal_grounding():
    """`audit:`/`fresh:` say the handbook is WRONG; they never say what the law
    IS. A draft citing only findings must still read as ungrounded, or the amber
    dot stops meaning "no legal citation"."""
    corpus = hp.build_corpus({**_grounding(), "audit": _audit(), "freshness": _freshness()})
    drafts = [{"id": "d1", "kind": "handbook_section", "title": "Sick Leave",
               "section_key": "sick_leave", "content": "body", "status": "pending",
               "promoted_ref": None,
               "citations": ["audit:ca-paid-sick-leave", "fresh:f0"]}]
    asm = hp.assemble_handbook({}, drafts, corpus)
    section = asm["sections"][0]
    assert section["law_citation_count"] == 0
    assert section["grounded"] is False
    # ...but the citations still resolve, so the admin can see what drove the draft
    assert {c["cid"] for c in section["citations"]} == {"audit:ca-paid-sick-leave", "fresh:f0"}


def test_prompt_forbids_citing_a_finding_as_law():
    assert "NOT law" in hp._SYSTEM
    corpus = hp.build_corpus({**_grounding(), "audit": _audit(), "freshness": _freshness()})
    text = hp._corpus_text(corpus)
    assert "[audit:ca-paid-sick-leave]" in text and "[fresh:f0]" in text
    assert "Handbook audit gaps" in text and "Handbook freshness findings" in text


def test_inline_cid_strips_every_namespace_from_prose():
    """Model-embedded corpus ids must not survive into employee-facing text —
    including the namespaces added after the regex was first written."""
    body = ("You accrue sick leave [law:ca-paid-sick-leave] per the governing rule "
            "[floor:state-california-paid-leave], see [audit:ca-paid-sick-leave] and "
            "[fresh:f0]. Contact [HR_CONTACT_EMAIL] or read [our policy](https://x.test).")
    cleaned = hp._INLINE_CID.sub("", body)
    for token in ("law:", "floor:", "audit:", "fresh:"):
        assert token not in cleaned
    assert "[HR_CONTACT_EMAIL]" in cleaned            # placeholders survive
    assert "[our policy](https://x.test)" in cleaned  # markdown links survive


def test_employee_redaction_covers_the_new_finding_groups():
    """Ask HR shares this corpus. The finding groups are empty for HR Pilot
    today, but the redaction list must already name them: whoever wires them in
    should not have to remember that an employee asking about PTO would
    otherwise be handed the company's own compliance gaps."""
    from app.matcha.services import hr_pilot_corpus as hpc
    assert "handbook_audit" in hpc._SUPERVISOR_ONLY_SOURCES
    assert "handbook_freshness" in hpc._SUPERVISOR_ONLY_SOURCES

    corpus = hp.build_corpus({**_grounding(), "audit": _audit(), "freshness": _freshness()})
    red = hpc.redact_for_employee(corpus)
    assert "handbook_audit" not in red["sources"] and "handbook_freshness" not in red["sources"]
    # cids leave the index too, so a guessed citation can't resolve either
    assert not any(c.startswith(("audit:", "fresh:")) for c in red["index"])
