"""HR Pilot citation corpus — pure-function tests (no DB, no network).

Covers the two things that make cited answers trustworthy: the corpus mints
stable, non-colliding ids, and the audit gate drops everything not in it.
"""

import pytest

from app.matcha.services.hr_pilot_corpus import (
    audit_citations,
    build_hr_pilot_corpus,
    render_corpus_block,
    _floor_records,
    _ladder_records,
)


# --------------------------------------------------------------------------- #
# Fixtures — minimal shapes matching what the real builders hand over.
# --------------------------------------------------------------------------- #

def _chain(location_label, category, level="state", juris="California",
           title="Meal and rest breaks", value="30 min unpaid after 5 hrs"):
    return {
        "location_id": "loc-1",
        "location_label": location_label,
        "categories": [{
            "category": category,
            "governing_level": level,
            "precedence_type": "floor",
            "legal_citation": "Cal. Lab. Code § 512",
            "reasoning_text": "State floor exceeds the federal baseline.",
            "all_levels": [
                {"jurisdiction_level": "federal", "jurisdiction_name": "Federal",
                 "title": "No federal meal requirement", "is_governing": False},
                {"jurisdiction_level": level, "jurisdiction_name": juris,
                 "title": title, "current_value": value, "is_governing": True,
                 "statute_citation": "Cal. Lab. Code § 512",
                 "source_url": "https://example.com/512",
                 "effective_date": "2024-01-01"},
            ],
        }],
    }


@pytest.fixture
def grounding():
    return {
        "scopes": ["CA"],
        "profile": {"legal_name": "Acme Co", "headcount": 120},
        "requirements": {
            "CA": [{"title": "Minimum wage", "category": "minimum_wage",
                    "current_value": "$16.00/hr", "jurisdiction_name": "California"}],
        },
        "sections": [{"id": "11111111-1111-1111-1111-111111111111",
                      "title": "Attendance", "content": "Call in two hours before shift."}],
        "policies": [{"id": "22222222-2222-2222-2222-222222222222",
                      "title": "Attendance Policy", "category": "attendance",
                      "status": "active", "description": "Two-hour call-in rule."}],
        "industry": "general",
    }


# --------------------------------------------------------------------------- #
# Floor records
# --------------------------------------------------------------------------- #

def test_floor_record_minted_from_governing_level():
    recs = _floor_records([_chain("Main Office", "meal_rest_breaks")])
    assert len(recs) == 1
    rec = recs[0]
    assert rec["cid"] == "floor:state-california-meal-rest-breaks"
    assert rec["category"] == "meal_rest_breaks"
    assert rec["governing_level"] == "state"
    # The GOVERNING level's title wins, not the first level in the list.
    assert "Meal and rest breaks" in rec["ref"]
    assert "30 min unpaid" in rec["summary"]
    assert rec["source_url"] == "https://example.com/512"


def test_same_obligation_across_locations_is_one_record():
    """Two offices in one state share one state obligation. Keying the cid on
    the location would mint it twice and the model would cite whichever copy it
    saw first."""
    recs = _floor_records([
        _chain("Main Office", "meal_rest_breaks"),
        _chain("Second Office", "meal_rest_breaks"),
    ])
    assert len(recs) == 1
    assert recs[0]["applies_to"] == ["Main Office", "Second Office"]


def test_distinct_jurisdictions_stay_distinct():
    recs = _floor_records([
        _chain("CA Office", "minimum_wage", juris="California", title="CA minimum wage"),
        _chain("NY Office", "minimum_wage", juris="New York", title="NY minimum wage"),
    ])
    assert len({r["cid"] for r in recs}) == 2


def test_local_and_state_same_category_do_not_collide():
    """A city ordinance and the state floor in the same category are different
    obligations — the level is part of the cid precisely so they don't merge."""
    recs = _floor_records([
        _chain("SF Office", "minimum_wage", level="state", juris="California"),
        _chain("SF Office", "minimum_wage", level="city", juris="San Francisco"),
    ])
    assert len({r["cid"] for r in recs}) == 2


def test_floor_records_tolerate_junk():
    assert _floor_records(None) == []
    assert _floor_records([]) == []
    assert _floor_records(["not a dict", {"categories": None}, {"categories": [{}]}]) == []


def test_floor_record_without_governing_level_still_mints():
    """No level flagged is_governing — the record must still be citable rather
    than vanishing, or the model has nothing to cite for that category."""
    chain = _chain("Main Office", "overtime")
    for lv in chain["categories"][0]["all_levels"]:
        lv["is_governing"] = False
    recs = _floor_records([chain])
    assert len(recs) == 1
    assert recs[0]["cid"].startswith("floor:state-state-overtime")


# --------------------------------------------------------------------------- #
# Ladder records
# --------------------------------------------------------------------------- #

def test_ladder_records_are_ordered_and_stable():
    recs = _ladder_records()
    assert [r["cid"] for r in recs] == [
        "ladder:verbal-warning", "ladder:written-warning",
        "ladder:final-warning", "ladder:termination-review",
    ]
    assert [r["step"] for r in recs] == [1, 2, 3, 4]


def test_termination_step_still_routes_to_hr():
    """The ladder became citable records; the hard-stop instruction it used to
    carry as prose must survive that move."""
    final = next(r for r in _ladder_records() if r["cid"] == "ladder:termination-review")
    assert "corporate HR" in final["summary"]


# --------------------------------------------------------------------------- #
# Corpus assembly
# --------------------------------------------------------------------------- #

def test_corpus_has_all_seven_groups(grounding):
    corpus = build_hr_pilot_corpus(grounding, [_chain("Main Office", "meal_rest_breaks")])
    assert set(corpus["sources"]) == {
        "profile", "law", "existing_handbook", "existing_policies",
        "playbook", "compliance_floor", "discipline_ladder",
    }


def test_index_covers_every_record(grounding):
    corpus = build_hr_pilot_corpus(grounding, [_chain("Main Office", "meal_rest_breaks")])
    total = sum(len(s["records"]) for s in corpus["sources"].values())
    assert len(corpus["index"]) == total, "a cid collision silently dropped a record"


def test_no_cid_collisions_across_groups(grounding):
    """The index is keyed by cid — a collision between two groups drops one
    record silently, so the namespaces must stay disjoint."""
    corpus = build_hr_pilot_corpus(grounding, [_chain("Main Office", "meal_rest_breaks")])
    seen = set()
    for source in corpus["sources"].values():
        for rec in source["records"]:
            assert rec["cid"] not in seen, f"duplicate cid {rec['cid']}"
            seen.add(rec["cid"])


def test_index_entries_carry_source_labels(grounding):
    corpus = build_hr_pilot_corpus(grounding, [_chain("Main Office", "meal_rest_breaks")])
    rec = corpus["index"]["ladder:verbal-warning"]
    assert rec["source"] == "discipline_ladder"
    assert rec["source_label"] == "Progressive discipline ladder"


def test_missing_floor_is_noted(grounding):
    corpus = build_hr_pilot_corpus(grounding, [])
    assert any("compliance floor" in n for n in corpus["notes"])


def test_empty_grounding_still_builds():
    """A brand-new tenant with nothing on file must yield a usable (ladder-only)
    corpus, not an exception."""
    corpus = build_hr_pilot_corpus({}, None)
    assert corpus["index"]
    assert all(cid.startswith(("ladder:", "playbook:")) for cid in corpus["index"])


def test_render_corpus_block_emits_every_cid(grounding):
    corpus = build_hr_pilot_corpus(grounding, [_chain("Main Office", "meal_rest_breaks")])
    block = render_corpus_block(corpus)
    for cid in corpus["index"]:
        assert f"[{cid}]" in block


def test_full_text_overrides_the_index_summary(grounding):
    """The record summary is a 280-char index entry. The model must see the real
    document — otherwise HR Pilot quotes the handbook from a preview of it."""
    long_body = "SECTION BODY. " + ("policy detail " * 200)   # ~2.8k chars
    grounding["sections"][0]["content"] = long_body
    corpus = build_hr_pilot_corpus(grounding, [])

    # The stored record stays index-sized so message metadata doesn't balloon.
    rec = corpus["index"]["handbook:11111111-1111-1111-1111-111111111111"]
    assert len(rec["summary"]) < 400

    block = render_corpus_block(
        corpus, {"handbook:11111111-1111-1111-1111-111111111111": long_body}
    )
    assert long_body in block
    assert len(block) > len(rec["summary"]) * 3


def test_render_falls_back_to_summary_without_full_text(grounding):
    corpus = build_hr_pilot_corpus(grounding, [])
    block = render_corpus_block(corpus, {})
    assert "Call in two hours before shift." in block


def test_policy_full_text_is_renderable(grounding):
    """Policy records carry title/category/description only — never the policy
    body — so without the override the model never sees the actual policy."""
    corpus = build_hr_pilot_corpus(grounding, [])
    cid = "policy:22222222-2222-2222-2222-222222222222"
    assert "FULL POLICY TEXT" not in corpus["index"][cid]["summary"]
    assert "FULL POLICY TEXT" in render_corpus_block(corpus, {cid: "FULL POLICY TEXT"})


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

@pytest.fixture
def index():
    return {
        "policy:22222222-2222-2222-2222-222222222222": {"cid": "policy:2222…", "ref": "Attendance Policy"},
        "ladder:verbal-warning": {"cid": "ladder:verbal-warning", "ref": "Verbal warning"},
    }


def test_known_citation_survives(index):
    text = "Start with a verbal warning [ladder:verbal-warning]."
    clean, cites, dropped = audit_citations(text, index)
    assert clean == text
    assert [c["ref"] for c in cites] == ["Verbal warning"]
    assert dropped == []


def test_invented_citation_is_stripped(index):
    clean, cites, dropped = audit_citations(
        "State law requires a 45-minute break [law:ca-breaks-invented].", index
    )
    assert "law:ca-breaks-invented" not in clean
    assert dropped == ["law:ca-breaks-invented"]
    assert cites == []
    # The claim survives, uncited and visibly unsupported — not a hole mid-sentence.
    assert clean == "State law requires a 45-minute break."


def test_mixed_citations_partition(index):
    clean, cites, dropped = audit_citations(
        "Per the policy [policy:22222222-2222-2222-2222-222222222222] "
        "and the statute [law:made-up], start with [ladder:verbal-warning].",
        index,
    )
    assert dropped == ["law:made-up"]
    assert len(cites) == 2
    assert "law:made-up" not in clean
    assert "policy:22222222-2222-2222-2222-222222222222" in clean


def test_citations_deduped_in_first_use_order(index):
    _, cites, _ = audit_citations(
        "[ladder:verbal-warning] then [policy:22222222-2222-2222-2222-222222222222] "
        "then [ladder:verbal-warning] again.",
        index,
    )
    assert [c["cid"] for c in cites] == ["ladder:verbal-warning", "policy:2222…"]


def test_dropped_ids_deduped(index):
    _, _, dropped = audit_citations("[law:x] and again [law:x].", index)
    assert dropped == ["law:x"]


def test_non_citation_brackets_untouched(index):
    """Markdown links and the corpus's own `[Handbook — Title]` headers are not
    citations; a greedy bracket regex would mangle them."""
    text = "See [the handbook](https://example.com) and [Acme Handbook — Attendance]."
    clean, cites, dropped = audit_citations(text, index)
    assert clean == text
    assert dropped == []
    assert cites == []


def test_bare_profile_cid_resolves():
    clean, cites, dropped = audit_citations(
        "Headcount is 120 [profile].", {"profile": {"cid": "profile", "ref": "Company profile"}}
    )
    assert dropped == []
    assert len(cites) == 1
    assert "[profile]" in clean


def test_empty_index_drops_everything(index):
    clean, cites, dropped = audit_citations("Rule [ladder:verbal-warning].", {})
    assert cites == []
    assert dropped == ["ladder:verbal-warning"]
    assert clean == "Rule."


def test_empty_text_is_safe(index):
    assert audit_citations("", index) == ("", [], [])
    assert audit_citations(None, index) == ("", [], [])


def test_no_citations_at_all_passes_through(index):
    text = "Talk to the employee first."
    clean, cites, dropped = audit_citations(text, index)
    assert (clean, cites, dropped) == (text, [], [])
