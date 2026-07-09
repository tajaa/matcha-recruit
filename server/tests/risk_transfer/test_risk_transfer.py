"""Pure tests for the contract risk-transfer verdict engine.

The verdicts feed an attorney-adjacent deliverable, so the tests bias toward the
failure modes that would silently produce a *confident wrong answer*: an
unmapped state read as "no statute", a choice-of-law clause papering over a
project-state anti-indemnity statute, or an unconfirmed AI extraction rendered
as settled fact.
"""

import pytest

from app.matcha.services import risk_transfer as rt
from app.matcha.services import limit_adequacy as la

M = 1_000_000


def _ind(**over):
    base = dict(present=True, form="broad", direction="we_indemnify_them",
                covers_sole_negligence=True, defense_obligation=True,
                quote="Contractor shall indemnify...", page=7)
    base.update(over)
    return {"indemnity": base}


def _contract(**over):
    c = {
        "id": "c1", "name": "Acme Subcontract", "counterparty": "Acme",
        "status": "parsed", "ai_available": True, "confirmed_at": None,
        "contract_type": "construction", "governing_state": "NY", "project_state": "NY",
        "storage_path": "s3://bucket/key", "risk_transfer": _ind(),
        "requirements": [],
    }
    c.update(over)
    return c


def _carried(**over):
    c = {"line": "gl", "per_occurrence": M, "aggregate": 2 * M, "retention": None,
         "carrier": "Carrier", "additional_insured": False, "waiver_of_subrogation": False,
         "primary_noncontributory": False, "effective_date": None, "expiry_date": None, "note": None}
    c.update(over)
    return c


def _req(line="gl", **over):
    r = {"line": line, "per_occurrence": 2 * M, "aggregate": None, "additional_insured": False,
         "waiver_of_subrogation": False, "primary_noncontributory": False, "note": None,
         "quote": None, "page": None}
    r.update(over)
    return r


# --- statute table shape ----------------------------------------------------

def test_statute_table_rows_are_well_formed():
    """Every row must carry a real citation and a known rule. A row without a
    citation is an inference, and inferences don't belong in this table."""
    assert rt._STATE_ANTI_INDEMNITY, "table must not be empty"
    for state, row in rt._STATE_ANTI_INDEMNITY.items():
        assert len(state) == 2 and state.isupper(), state
        assert row["rule"] in ("own_negligence_void", "sole_negligence_void", "none"), state
        assert row["statute"] and any(ch.isdigit() for ch in row["statute"]), state


def test_table_is_partial_and_unmapped_states_never_read_as_no_statute():
    assert "WY" not in rt._STATE_ANTI_INDEMNITY
    v = rt.assess_indemnity(_ind(), project_state="WY", contract_type="construction")
    assert v["verdict"] == rt.VERDICT_REVIEW
    assert "not in our reference table" in v["basis"]


# --- construction: project state controls -----------------------------------

def test_project_state_controls_construction_over_choice_of_law():
    """A DE choice-of-law clause must not escape NY's anti-indemnity statute for
    work performed in NY — the statutes are anti-waiver."""
    v = rt.assess_indemnity(_ind(), governing_state="DE", project_state="NY",
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_VOID
    assert v["controlling_state"] == "NY"
    assert v["statute"] == "N.Y. Gen. Oblig. Law § 5-322.1"


def test_conflicting_mapped_states_degrade_to_review():
    """GA voids only sole-negligence indemnity; NY voids any. When the project and
    governing states disagree on the RULE, the honest answer is 'ask counsel'."""
    v = rt.assess_indemnity(_ind(), governing_state="GA", project_state="NY",
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_REVIEW
    assert "anti-waiver" in v["basis"]


def test_agreeing_states_do_not_trigger_the_conflict_path():
    v = rt.assess_indemnity(_ind(), governing_state="NY", project_state="NY",
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_VOID


def test_conflict_path_ignores_states_with_the_same_rule():
    """NY and IL both void own-negligence indemnity — differing states, same rule,
    so there is nothing for counsel to resolve."""
    v = rt.assess_indemnity(_ind(), governing_state="IL", project_state="NY",
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_VOID
    assert v["controlling_state"] == "NY"


def test_non_construction_uses_governing_state():
    v = rt.assess_indemnity(_ind(form="intermediate", covers_sole_negligence=False),
                            governing_state="NY", project_state="GA", contract_type="msa")
    assert v["controlling_state"] == "NY"


# --- verdict matrix ---------------------------------------------------------

@pytest.mark.parametrize("state,form,sole,expected", [
    # own_negligence_void state (NY): both broad and intermediate die.
    ("NY", "broad", True, rt.VERDICT_VOID),
    ("NY", "intermediate", False, rt.VERDICT_VOID),
    ("NY", "limited", False, rt.VERDICT_INSURABLE),
    # sole_negligence_void state (GA): only broad dies.
    ("GA", "broad", True, rt.VERDICT_VOID),
    ("GA", "intermediate", False, rt.VERDICT_INSURABLE),
    ("GA", "limited", False, rt.VERDICT_INSURABLE),
])
def test_construction_verdict_matrix(state, form, sole, expected):
    v = rt.assess_indemnity(_ind(form=form, covers_sole_negligence=sole),
                            project_state=state, contract_type="construction")
    assert v["verdict"] == expected


def test_broad_form_implies_sole_negligence_even_if_flag_unset():
    """`form` is authoritative — a broad-form clause covers sole negligence by
    definition, so an unset boolean must not downgrade the verdict."""
    v = rt.assess_indemnity(_ind(form="broad", covers_sole_negligence=False),
                            project_state="GA", contract_type="construction")
    assert v["verdict"] == rt.VERDICT_VOID


def test_non_construction_broad_form_is_uninsurable_not_void():
    v = rt.assess_indemnity(_ind(), governing_state="NY", contract_type="lease")
    assert v["verdict"] == rt.VERDICT_UNINSURABLE
    assert "insured contract" in v["basis"]


def test_non_construction_intermediate_and_limited_are_insurable():
    for form in ("intermediate", "limited"):
        v = rt.assess_indemnity(_ind(form=form, covers_sole_negligence=False),
                                governing_state="NY", contract_type="vendor_service")
        assert v["verdict"] == rt.VERDICT_INSURABLE


def test_counterparty_indemnifies_us_is_never_our_exposure():
    v = rt.assess_indemnity(_ind(direction="they_indemnify_us"),
                            project_state="NY", contract_type="construction")
    assert v["verdict"] == rt.VERDICT_INSURABLE


# --- review (unknown) paths -------------------------------------------------

@pytest.mark.parametrize("rtx,kwargs", [
    (None, {}),
    ({}, {}),
    ({"indemnity": {"present": False}}, {}),
    (_ind(form="unclear"), dict(project_state="NY", contract_type="construction")),
    (_ind(form="bogus"), dict(project_state="NY", contract_type="construction")),
    (_ind(), dict(contract_type="construction")),                       # no state at all
    (_ind(), dict(project_state="ZZZ", contract_type="construction")),  # malformed state
])
def test_unknowns_degrade_to_review(rtx, kwargs):
    assert rt.assess_indemnity(rtx, **kwargs)["verdict"] == rt.VERDICT_REVIEW


def test_assess_indemnity_accepts_a_bare_indemnity_dict():
    """`risk_transfer` may be stored either wrapped or bare; both must work."""
    bare = _ind()["indemnity"]
    assert rt.assess_indemnity(bare, project_state="NY", contract_type="construction")["verdict"] == rt.VERDICT_VOID


# --- per-contract review ----------------------------------------------------

def test_review_contract_diffs_this_contract_only():
    """The portfolio `analyze` takes the max across all contracts; the per-contract
    review must see only its own requirement."""
    c = _contract(requirements=[_req("gl", per_occurrence=2 * M)])
    other = _contract(id="c2", requirements=[_req("gl", per_occurrence=10 * M)])
    review = rt.review_contract(c, [_carried()], headcount=50)
    gl = {l["key"]: l for l in review["lines"]}["gl"]
    assert gl["status"] == "shortfall"
    assert gl["contract_required"]["per_occurrence"] == 2 * M

    portfolio = la.analyze([_carried()], [c, other], headcount=50, venue_tier=None)
    assert {l["key"]: l for l in portfolio["lines"]}["gl"]["contract_required"]["per_occurrence"] == 10 * M


def test_review_contract_summary_and_actions():
    c = _contract(requirements=[
        _req("gl", per_occurrence=2 * M, additional_insured=True),
        _req("cyber", per_occurrence=M),
    ])
    review = rt.review_contract(c, [_carried()], headcount=120, venue_tier="high")
    assert review["summary"]["indemnity_verdict"] == rt.VERDICT_VOID
    assert review["summary"]["exposed"] == 2          # gl shortfall + cyber no_coverage
    assert review["summary"]["endorsement_gaps"] == 1  # additional insured
    joined = " ".join(review["actions"])
    assert "Strike or narrow the indemnity clause" in joined
    assert "additional insured endorsement" in joined
    assert review["disclaimer"] == la.DISCLAIMER


def test_unconfirmed_extraction_is_provisional_and_prompts_confirmation():
    review = rt.review_contract(_contract(confirmed_at=None), [], headcount=10)
    assert review["provisional"] is True
    assert any("Confirm the extracted terms" in a for a in review["actions"])


def test_confirmed_extraction_is_not_provisional():
    review = rt.review_contract(_contract(confirmed_at="2026-07-09T00:00:00Z"), [], headcount=10)
    assert review["provisional"] is False
    assert not any("Confirm the extracted terms" in a for a in review["actions"])


def test_review_contract_reports_source_retention():
    assert rt.review_contract(_contract(), [], headcount=1)["contract"]["has_source"] is True
    assert rt.review_contract(_contract(storage_path=None), [], headcount=1)["contract"]["has_source"] is False


def test_insurable_contract_yields_no_indemnity_action():
    c = _contract(risk_transfer=_ind(form="limited", covers_sole_negligence=False),
                  confirmed_at="2026-07-09T00:00:00Z")
    review = rt.review_contract(c, [], headcount=10)
    assert review["indemnity"]["verdict"] == rt.VERDICT_INSURABLE
    assert review["actions"] == []


# --- rendering --------------------------------------------------------------

def test_review_html_marks_provisional_and_escapes_clause_text():
    c = _contract(risk_transfer=_ind(quote='Indemnify <Owner> & "Agents"'))
    review = rt.review_contract(c, [], headcount=10)
    review["company_name"] = "Test Co"
    html = rt._contract_review_html(review)
    assert "PROVISIONAL" in html
    assert la.DISCLAIMER in html
    assert "&lt;Owner&gt;" in html and "<Owner>" not in html


def test_risk_transfer_rows_html_uses_the_caller_supplied_class_map():
    """The two stylesheets name status classes differently; the shared row builder
    must not hard-code either one."""
    review = {"contracts": [{
        "name": "Acme", "contract_type": "construction", "project_state": "NY",
        "provisional": False, "risk_transfer": _ind(),
        "indemnity": {"verdict": rt.VERDICT_VOID, "statute": "N.Y. Gen. Oblig. Law § 5-322.1"},
    }]}
    rows = la.risk_transfer_rows_html(review, verdict_class={"likely_void_by_statute": "lim-bad"})
    assert "lim-bad" in rows and "st bad" not in rows
    assert "LIKELY VOID" in rows


def test_risk_transfer_rows_skip_contracts_with_no_clause_and_no_type():
    review = {"contracts": [{"name": "Bare", "risk_transfer": None, "indemnity": {"verdict": "review"}}]}
    assert la.risk_transfer_rows_html(review) == ""
