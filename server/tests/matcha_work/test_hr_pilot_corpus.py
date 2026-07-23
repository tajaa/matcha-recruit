"""HR Pilot citation corpus — pure-function tests (no DB, no network).

Covers the two things that make cited answers trustworthy: the corpus mints
stable, non-colliding ids, and the audit gate drops everything not in it.
"""

import pytest

from datetime import date, datetime, timedelta

from app.matcha.services.hr_pilot_corpus import (
    audit_citations,
    build_hr_pilot_corpus,
    render_corpus_block,
    _MAX_BENEFIT_PLANS,
    _MAX_SCHEDULE_SHIFTS,
    _MAX_TRAINING_DETAIL,
    _benefit_records,
    _floor_records,
    _incident_records,
    _ladder_records,
    _schedule_records,
    _training_records,
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

def test_policy_groups_present_without_operational_data(grounding):
    """Grounding with no operational keys at all (the pre-Copilot shape) still
    builds — the operational groups appear empty rather than the build failing.
    Group membership as a whole is asserted by test_corpus_has_ten_groups."""
    corpus = build_hr_pilot_corpus(grounding, [_chain("Main Office", "meal_rest_breaks")])
    assert {"profile", "law", "existing_handbook", "existing_policies",
            "playbook", "compliance_floor", "discipline_ladder"} <= set(corpus["sources"])
    assert corpus["sources"]["schedule"]["records"] == []


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


# --------------------------------------------------------------------------- #
# Supervisor Copilot — operational-fact groups
# --------------------------------------------------------------------------- #

def _shift(sid="aaaaaaaa-0000-0000-0000-000000000001", names=("Ana Ruiz",),
           required=2, role="Line Cook", start=None):
    start = start or datetime(2026, 7, 25, 9, 0)
    return {
        "id": sid, "role": role, "department": "Kitchen",
        "starts_at": start, "ends_at": start + timedelta(hours=8),
        "required_staff": required, "location_id": None,
        "assignees": [{"name": n, "job_title": role, "status": "assigned"} for n in names],
    }


def test_schedule_record_names_assignees_and_weekday():
    rec = _schedule_records([_shift()])[0]
    assert rec["cid"] == "schedule:aaaaaaaa-0000-0000-0000-000000000001"
    assert "Ana Ruiz" in rec["summary"]
    # Weekday must survive — "who's on Saturday" is the driving question, and
    # the model must not have to derive the day from an ISO date.
    assert "Sat" in rec["when"]


def test_schedule_record_computes_shortfall():
    """Staffing gap is arithmetic, computed here — not left to the model."""
    rec = _schedule_records([_shift(names=("Ana Ruiz",), required=3)])[0]
    assert "SHORT BY 2" in rec["summary"]


def test_schedule_record_flags_fully_staffed():
    rec = _schedule_records([_shift(names=("Ana Ruiz", "Bo Lee"), required=2)])[0]
    assert "fully staffed" in rec["summary"]


def test_schedule_record_handles_empty_shift():
    rec = _schedule_records([_shift(names=())])[0]
    assert "nobody assigned" in rec["summary"]


def test_schedule_records_parse_json_assignees():
    """asyncpg hands json_agg back as a string on some paths."""
    s = _shift()
    s["assignees"] = '[{"name": "Ana Ruiz", "job_title": "Cook", "status": "assigned"}]'
    assert "Ana Ruiz" in _schedule_records([s])[0]["summary"]


def test_schedule_records_tolerate_junk():
    assert _schedule_records(None) == []
    assert _schedule_records(["nope", {}, {"id": None}]) == []


def _training_fixture():
    return {
        "programs": [{"id": "bbbbbbbb-0000-0000-0000-000000000001", "title": "Food Safety",
                      "training_type": "safety", "frequency_months": 12,
                      "total_assigned": 10, "completed": 7, "overdue": 2}],
        "overdue": [{"id": "cccccccc-0000-0000-0000-000000000001", "title": "Food Safety",
                     "due_date": date(2026, 7, 1), "first_name": "Ana", "last_name": "Ruiz",
                     "job_title": "Cook"}],
        "expiring": [{"id": "dddddddd-0000-0000-0000-000000000001", "title": "Food Safety",
                      "expiration_date": date(2026, 8, 15), "first_name": "Bo",
                      "last_name": "Lee", "job_title": "Cook"}],
    }


def test_training_program_record_computes_completion_pct():
    recs = _training_records(_training_fixture())
    prog = next(r for r in recs if r["cid"].startswith("training:program-"))
    assert "7/10 complete (70%)" in prog["summary"]
    assert "2 OVERDUE" in prog["summary"]


def test_training_detail_records_name_the_person():
    recs = _training_records(_training_fixture())
    overdue = next(r for r in recs if r.get("status") == "overdue")
    expiring = next(r for r in recs if r.get("status") == "expiring")
    assert "Ana Ruiz" in overdue["summary"]
    assert "Bo Lee" in expiring["summary"]


def test_training_cids_program_and_detail_are_disjoint():
    """Two cid shapes share one namespace; a raw UUID can never collide with a
    `program-` prefix, which is what keeps the flat index sound."""
    recs = _training_records(_training_fixture())
    cids = [r["cid"] for r in recs]
    assert len(cids) == len(set(cids))
    assert sum(1 for c in cids if c.startswith("training:program-")) == 1


def test_training_records_never_expose_scores_or_certificates():
    """Credential precedent: status and dates only."""
    fixture = _training_fixture()
    fixture["overdue"][0]["score"] = 91
    fixture["overdue"][0]["certificate_number"] = "SECRET-123"
    blob = repr(_training_records(fixture))
    assert "SECRET-123" not in blob
    assert "91" not in blob


def test_training_records_tolerate_junk():
    assert _training_records(None) == []
    assert _training_records({}) == []


def test_incident_records_name_no_people():
    recs = _incident_records([{
        "id": "eeeeeeee-0000-0000-0000-000000000001", "incident_number": "IR-4",
        "title": "Slip in walk-in", "incident_type": "safety", "severity": "medium",
        "status": "open", "occurred_at": datetime(2026, 7, 10), "location": "Kitchen",
        "involved_employee_ids": ["should-never-render"],
    }])
    assert recs[0]["cid"] == "incident:eeeeeeee-0000-0000-0000-000000000001"
    assert "should-never-render" not in repr(recs)


def test_incident_records_tolerate_junk():
    assert _incident_records(None) == []
    assert _incident_records([{}, "x"]) == []


# --- corpus integration ----------------------------------------------------- #

def _benefit_fixture():
    return {
        "plans": [{
            "id": "eeeeeeee-0000-0000-0000-000000000001", "plan_type": "medical",
            "name": "Gold PPO", "carrier_name": "Acme Health", "waivable": True,
            "tiers": [
                {"coverage_tier": "employee_only", "employee_cost": 120.0, "cost_period": "monthly"},
                {"coverage_tier": "family", "employee_cost": 480.5, "cost_period": "monthly"},
            ],
        }],
        "open_period": {"id": "ffffffff-0000-0000-0000-000000000001",
                        "name": "2027 Plan Year", "starts_on": date(2026, 11, 1),
                        "ends_on": date(2026, 11, 15), "plan_year_start": date(2027, 1, 1)},
        "submitted_employees": 12,
        "active_employees": 40,
        "pending_life_events": 2,
    }


def _ops(grounding, **over):
    g = dict(grounding)
    g.update({"shifts": [_shift()], "training": _training_fixture(),
              "incidents": [], "benefits": _benefit_fixture(), **over})
    return g


def test_corpus_has_thirteen_groups(grounding):
    corpus = build_hr_pilot_corpus(_ops(grounding), [])
    assert set(corpus["sources"]) == {
        "profile", "law", "existing_handbook", "existing_policies", "playbook",
        "compliance_floor", "discipline_ladder",
        "schedule", "training_status", "recent_incidents", "benefits",
        # Minted by the shared `handbook_pilot.build_corpus` and always EMPTY
        # here: `gather_hr_pilot_grounding` doesn't fetch audit gaps or freshness
        # findings (a supervisor needs the rule in force, not a list of where the
        # handbook falls short). Empty groups render nothing in the prompt.
        "handbook_audit", "handbook_freshness",
    }


def test_the_finding_groups_stay_empty_for_hr_pilot(grounding):
    corpus = build_hr_pilot_corpus(_ops(grounding), [])
    assert corpus["sources"]["handbook_audit"]["records"] == []
    assert corpus["sources"]["handbook_freshness"]["records"] == []
    assert not any(c.startswith(("audit:", "fresh:")) for c in corpus["index"])


def test_no_cid_collisions_with_operational_groups(grounding):
    corpus = build_hr_pilot_corpus(_ops(grounding), [_chain("Main Office", "meal_rest_breaks")])
    seen = set()
    for source in corpus["sources"].values():
        for rec in source["records"]:
            assert rec["cid"] not in seen, f"duplicate cid {rec['cid']}"
            seen.add(rec["cid"])
    total = sum(len(s["records"]) for s in corpus["sources"].values())
    assert len(corpus["index"]) == total


def test_module_off_emits_a_note_but_empty_does_not(grounding):
    """`None` (module off) and `[]` (on, nothing there) are different answers to
    "who's on Saturday" — one is "this company doesn't schedule here"."""
    off = build_hr_pilot_corpus(_ops(grounding, shifts=None), [])
    assert any("not enabled" in n and "schedul" in n.lower() for n in off["notes"])

    empty = build_hr_pilot_corpus(_ops(grounding, shifts=[]), [])
    assert not any("Shift scheduling is not enabled" in n for n in empty["notes"])


def test_each_operational_module_has_its_own_off_note(grounding):
    corpus = build_hr_pilot_corpus(
        _ops(grounding, shifts=None, training=None, incidents=None, benefits=None), [])
    notes = " ".join(corpus["notes"]).lower()
    assert "shift scheduling is not enabled" in notes
    assert "training records are not enabled" in notes
    assert "incident reporting is not enabled" in notes
    assert "benefits enrollment is not enabled" in notes


def test_cap_hit_emits_truncation_note(grounding):
    many = [_shift(sid=f"aaaaaaaa-0000-0000-0000-{i:012d}") for i in range(_MAX_SCHEDULE_SHIFTS)]
    corpus = build_hr_pilot_corpus(_ops(grounding, shifts=many), [])
    assert any("do not treat the list as complete" in n for n in corpus["notes"])


def test_training_cap_note(grounding):
    t = _training_fixture()
    t["overdue"] = [dict(t["overdue"][0], id=f"cccccccc-0000-0000-0000-{i:012d}")
                    for i in range(_MAX_TRAINING_DETAIL)]
    corpus = build_hr_pilot_corpus(_ops(grounding, training=t), [])
    assert any("capped at" in n for n in corpus["notes"])


def test_audit_gate_resolves_new_namespaces(grounding):
    corpus = build_hr_pilot_corpus(_ops(grounding), [])
    index = corpus["index"]
    text = ("Ana is on [schedule:aaaaaaaa-0000-0000-0000-000000000001] but is overdue "
            "on [training:cccccccc-0000-0000-0000-000000000001], and [schedule:invented] "
            "does not exist.")
    clean, cites, dropped = audit_citations(text, index)
    assert dropped == ["schedule:invented"]
    assert {c["cid"] for c in cites} == {
        "schedule:aaaaaaaa-0000-0000-0000-000000000001",
        "training:cccccccc-0000-0000-0000-000000000001",
    }
    assert "schedule:invented" not in clean


def test_operational_records_render_into_the_prompt_block(grounding):
    corpus = build_hr_pilot_corpus(_ops(grounding), [])
    block = render_corpus_block(corpus)
    assert "PUBLISHED SHIFTS" in block.upper()
    assert "Ana Ruiz" in block
    for cid in corpus["index"]:
        assert f"[{cid}]" in block


# --------------------------------------------------------------------------- #
# Review fixes — employee redaction, declined assignees, unknown-feature state
# --------------------------------------------------------------------------- #

from app.matcha.services.hr_pilot_corpus import (  # noqa: E402
    _SUPERVISOR_ONLY_SOURCES,
    redact_for_employee,
)


def test_redaction_removes_operational_groups(grounding):
    """Employee Ask HR shares this corpus. Schedule/training/incident records
    name coworkers — an employee asking about PTO must not be able to pull a
    roster or a list of who failed a training out of it."""
    corpus = build_hr_pilot_corpus(_ops(grounding), [])
    assert any(k in corpus["sources"] for k in _SUPERVISOR_ONLY_SOURCES)

    safe = redact_for_employee(corpus)
    for key in _SUPERVISOR_ONLY_SOURCES:
        assert key not in safe["sources"]
    # Policy material survives — that IS the employee's answer.
    assert "existing_policies" in safe["sources"]
    assert "compliance_floor" in safe["sources"]


def test_redaction_strips_cids_from_the_index_too(grounding):
    """Removing the group but leaving its cids indexed would let a guessed
    citation resolve, laundering a record the model was never shown."""
    safe = redact_for_employee(build_hr_pilot_corpus(_ops(grounding), []))
    assert not [c for c in safe["index"] if c.startswith(("schedule:", "training:", "incident:"))]
    assert any(c.startswith("policy:") for c in safe["index"])


def test_redacted_corpus_drops_coworker_names(grounding):
    """The actual leak: a name in a training record."""
    corpus = build_hr_pilot_corpus(_ops(grounding), [])
    assert "Ana Ruiz" in repr(corpus)
    assert "Ana Ruiz" not in repr(redact_for_employee(corpus))


def test_redaction_gate_rejects_operational_citations(grounding):
    """End-to-end: the audit gate run against a redacted index must drop a
    schedule citation, not resolve it."""
    safe = redact_for_employee(build_hr_pilot_corpus(_ops(grounding), []))
    _, cites, dropped = audit_citations(
        "Ana works Saturday [schedule:aaaaaaaa-0000-0000-0000-000000000001].", safe["index"])
    assert cites == []
    assert dropped == ["schedule:aaaaaaaa-0000-0000-0000-000000000001"]


def test_redaction_tolerates_empty_corpus():
    out = redact_for_employee({})
    assert out == {"sources": {}, "index": {}, "notes": []}


def test_declined_assignees_are_not_counted_as_staffed():
    """A declined assignment rendered as 'assigned … fully staffed' answers
    'is Saturday covered?' with a confident, cited, wrong yes."""
    s = _shift(names=("Ana Ruiz", "Bo Lee"), required=2)
    s["assignees"][1]["status"] = "declined"
    rec = _schedule_records([s])[0]
    assert "Bo Lee" not in rec["summary"]
    assert "SHORT BY 1" in rec["summary"]


def test_unknown_features_do_not_claim_modules_are_off(grounding):
    """A failed feature lookup leaves the operational keys ABSENT. Reporting
    that as 'not enabled' tells a paying customer they lost a product."""
    g = dict(grounding)
    g["features_known"] = False
    corpus = build_hr_pilot_corpus(g, [])
    notes = " ".join(corpus["notes"])
    assert "not enabled" not in notes
    assert "temporarily" in notes.lower() or "briefly unavailable" in notes.lower()


def test_module_off_still_says_not_enabled(grounding):
    """The explicit-None path must keep its original behaviour."""
    g = _ops(grounding, shifts=None)
    g["features_known"] = True
    assert any("Shift scheduling is not enabled" in n
               for n in build_hr_pilot_corpus(g, [])["notes"])


def test_training_program_cap_note(grounding):
    from app.matcha.services.hr_pilot_corpus import _MAX_TRAINING_PROGRAMS
    t = _training_fixture()
    t["programs"] = [dict(t["programs"][0], id=f"bbbbbbbb-0000-0000-0000-{i:012d}")
                     for i in range(_MAX_TRAINING_PROGRAMS)]
    corpus = build_hr_pilot_corpus(_ops(grounding, training=t), [])
    assert any("training programs are listed" in n for n in corpus["notes"])


# --------------------------------------------------------------------------- #
# Benefits enrollment group — the one operational group Ask HR keeps
# --------------------------------------------------------------------------- #

def test_benefit_plan_record_carries_tiers_and_waivability():
    recs = _benefit_records(_benefit_fixture())
    plan = next(r for r in recs if r["cid"] == "benefit:plan-eeeeeeee-0000-0000-0000-000000000001")
    assert "Gold PPO" in plan["ref"]
    assert "$120.00/mo" in plan["summary"]
    assert "$480.50/mo" in plan["summary"]
    assert "can be waived" in plan["summary"]


def test_benefit_oe_record_states_window_and_progress():
    recs = _benefit_records(_benefit_fixture())
    oe = next(r for r in recs if r["cid"] == "benefit:oe-ffffffff-0000-0000-0000-000000000001")
    assert "2026-11-15" in oe["summary"]
    assert "coverage effective 2027-01-01" in oe["summary"]
    assert "12 of 40" in oe["summary"]


def test_benefit_life_event_record_is_a_nameless_aggregate():
    recs = _benefit_records(_benefit_fixture())
    le = next(r for r in recs if r["cid"] == "benefit:life-events-pending")
    assert "2 qualifying life-event" in le["summary"]


def test_benefit_records_parse_json_tiers():
    """asyncpg hands json_agg back as a string on some paths."""
    b = _benefit_fixture()
    b["plans"][0]["tiers"] = (
        '[{"coverage_tier": "employee_only", "employee_cost": 120, "cost_period": "per_pay_period"}]'
    )
    rec = _benefit_records(b)[0]
    assert "$120.00/pay period" in rec["summary"]


def test_benefit_records_tolerate_junk():
    assert _benefit_records(None) == []
    assert _benefit_records({}) == []
    assert _benefit_records({"plans": ["nope", {"id": None}], "open_period": "junk",
                             "pending_life_events": 0}) == []


def test_benefit_records_name_no_people():
    """The invariant that lets this group skip _SUPERVISOR_ONLY_SOURCES: no
    record field carries an employee name — only plans, the window, counts."""
    for rec in _benefit_records(_benefit_fixture()):
        assert "employee_name" not in rec
        assert "assignee_names" not in rec


def test_redaction_keeps_benefits_for_employees(grounding):
    """"When does open enrollment close?" is a core Ask HR question — the
    benefits group (nameless by construction) must survive redaction while
    schedule/training/incidents are stripped."""
    safe = redact_for_employee(build_hr_pilot_corpus(_ops(grounding), []))
    assert "benefits" in safe["sources"]
    assert any(c.startswith("benefit:") for c in safe["index"])
    assert not any(c.startswith(("schedule:", "training:", "incident:")) for c in safe["index"])


def test_benefits_off_note_survives_employee_redaction(grounding):
    """The module-off note is deliberately worded around redact_for_employee's
    substring filter — if someone rewords it with 'shifts'/'incidents' in it,
    employees lose the 'we don't have this module' answer."""
    corpus = build_hr_pilot_corpus(_ops(grounding, benefits=None), [])
    safe = redact_for_employee(corpus)
    assert any("Benefits enrollment is not enabled" in n for n in safe["notes"])


def test_benefit_plan_cap_note(grounding):
    b = _benefit_fixture()
    b["plans"] = [dict(b["plans"][0], id=f"eeeeeeee-0000-0000-0000-{i:012d}")
                  for i in range(_MAX_BENEFIT_PLANS)]
    corpus = build_hr_pilot_corpus(_ops(grounding, benefits=b), [])
    assert any("benefit plans are listed" in n for n in corpus["notes"])


def test_audit_gate_resolves_benefit_namespace(grounding):
    corpus = build_hr_pilot_corpus(_ops(grounding), [])
    text = ("Open enrollment closes Nov 15 [benefit:oe-ffffffff-0000-0000-0000-000000000001], "
            "and [benefit:plan-invented] does not exist.")
    clean, cites, dropped = audit_citations(text, corpus["index"])
    assert dropped == ["benefit:plan-invented"]
    assert {c["cid"] for c in cites} == {"benefit:oe-ffffffff-0000-0000-0000-000000000001"}
