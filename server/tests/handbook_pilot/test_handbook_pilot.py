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
