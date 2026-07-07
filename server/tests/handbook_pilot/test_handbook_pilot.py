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


def test_build_corpus_notes_when_no_scopes():
    g = _grounding()
    g["scopes"] = []
    g["requirements"] = {}
    corpus = hp.build_corpus(g)
    assert corpus["notes"], "expected a note when no work locations are on file"


def test_build_corpus_tolerates_empty_grounding():
    corpus = hp.build_corpus({})
    assert corpus["index"] == {}
    assert isinstance(corpus["sources"], dict)


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
    # a second law record nobody cites → an uncovered / candidate-gap requirement
    idx["law:ca-osha-1"] = {"ref": "CA OSHA log", "summary": "",
                            "source": "law", "source_label": "Applicable jurisdiction requirements"}
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
