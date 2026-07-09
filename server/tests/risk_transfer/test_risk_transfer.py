"""Pure tests for the contract risk-transfer verdict engine.

The verdicts feed an attorney-adjacent deliverable, so the tests bias toward the
failure modes that would silently produce a *confident wrong answer*: an
unmapped state read as "no statute", a choice-of-law clause papering over a
project-state anti-indemnity statute, or an unconfirmed AI extraction rendered
as settled fact.
"""

import json

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
        "has_source": True, "risk_transfer": _ind(),
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


@pytest.mark.parametrize("form", ["intermediate", "limited"])
def test_table_is_partial_and_unmapped_states_never_read_as_no_statute(form):
    """An unmapped state must never resolve the ENFORCEABILITY question — silence
    is not "no statute". Only non-broad forms reach this, because broad form is
    decided by the state-independent CGL analysis below."""
    assert "WY" not in rt._STATE_ANTI_INDEMNITY
    v = rt.assess_indemnity(_ind(form=form, covers_sole_negligence=False),
                            project_state="WY", contract_type="construction")
    assert v["verdict"] == rt.VERDICT_REVIEW
    assert "not in our reference table" in v["basis"]


def test_unmapped_construction_state_does_not_suppress_the_cgl_analysis():
    """Insurability under the CGL insured-contract grant is state-independent. An
    unmapped state resolves only enforceability, so a broad-form clause is still
    an uninsurable exposure — the same finding a lease in the same state gets."""
    v = rt.assess_indemnity(_ind(), project_state="WY", contract_type="construction")
    assert v["verdict"] == rt.VERDICT_UNINSURABLE
    assert "SOLE negligence" in v["basis"]
    assert "not in our reference table" in v["basis"]  # enforceability still flagged open
    lease = rt.assess_indemnity(_ind(), governing_state="WY", contract_type="lease")
    assert lease["verdict"] == v["verdict"]


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
    v = rt.assess_indemnity(_ind(form="intermediate", covers_sole_negligence=False),
                            governing_state="GA", project_state="NY",
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_REVIEW
    assert "anti-waiver" in v["basis"]


def test_conflicting_states_still_yield_the_state_independent_finding():
    """The conflict blocks the VOID ruling, not the CGL one — a broad-form clause
    is uninsurable whichever of the two states ends up controlling."""
    v = rt.assess_indemnity(_ind(), governing_state="GA", project_state="NY",
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_UNINSURABLE
    assert "anti-waiver" in v["basis"]  # the unresolved enforceability is still surfaced


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
    # No usable state → the statute lookup is blocked. Non-broad forms have nothing
    # left to rule on; broad form still gets the state-independent CGL finding
    # (see test_missing_project_state_still_yields_the_state_independent_finding).
    (_ind(form="intermediate", covers_sole_negligence=False),
     dict(contract_type="construction")),                                # no state at all
    (_ind(form="intermediate", covers_sole_negligence=False),
     dict(project_state="ZZZ", contract_type="construction")),           # malformed state
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
    assert rt.review_contract(_contract(has_source=False), [], headcount=1)["contract"]["has_source"] is False


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


# --- regressions from the PR review -----------------------------------------
#
# Every case below is an UNKNOWN input that previously escaped the
# "unknowns degrade to review" invariant and produced a confident verdict.

def test_construction_without_project_state_never_falls_back_to_governing_state():
    """The governing state is exactly what anti-waiver statutes ignore. A blank
    project state must block the verdict, not silently substitute NY law."""
    v = rt.assess_indemnity(_ind(form="intermediate", covers_sole_negligence=False),
                            governing_state="NY", project_state=None,
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_REVIEW
    assert "where the work is performed" in v["basis"]
    assert "NY" in v["basis"]  # names the state it refused to use


def test_missing_project_state_still_yields_the_state_independent_finding():
    """A blank project state blocks the statute lookup, not the CGL analysis."""
    v = rt.assess_indemnity(_ind(), governing_state="NY", project_state=None,
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_UNINSURABLE
    assert "where the work is performed" in v["basis"]
    assert v["controlling_state"] is None


@pytest.mark.parametrize("form,expected", [
    ("broad", rt.VERDICT_UNINSURABLE),
    ("intermediate", rt.VERDICT_INSURABLE),
    ("limited", rt.VERDICT_INSURABLE),
])
def test_a_no_statute_state_never_relabels_broad_form_as_limited(monkeypatch, form, expected):
    """A `rule: "none"` row means the statute doesn't VOID the clause — it does not
    mean the CGL grant funds it. Broad form must not fall through to the
    limited-form 'Enforceable and covered' return."""
    monkeypatch.setitem(rt._STATE_ANTI_INDEMNITY, "ZZ",
                        {"rule": "none", "statute": "Hyp. Rev. Code § 1"})
    v = rt.assess_indemnity(_ind(form=form, covers_sole_negligence=(form == "broad")),
                            project_state="ZZ", contract_type="construction")
    assert v["verdict"] == expected
    if form == "broad":
        assert "Limited-form" not in v["basis"]


def test_construction_with_only_a_project_state_still_rules():
    v = rt.assess_indemnity(_ind(), governing_state=None, project_state="NY",
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_VOID


@pytest.mark.parametrize("state", [None, "WY", "NY"])
def test_non_construction_insurability_is_state_independent(state):
    """The CGL 'insured contract' analysis needs no statute table — an unmapped
    or absent state must not suppress an uninsurable-exposure finding."""
    v = rt.assess_indemnity(_ind(), governing_state=state, contract_type="lease")
    assert v["verdict"] == rt.VERDICT_UNINSURABLE


@pytest.mark.parametrize("state", [None, "WY"])
def test_non_construction_limited_form_is_insurable_without_a_statute(state):
    v = rt.assess_indemnity(_ind(form="limited", covers_sole_negligence=False),
                            governing_state=state, contract_type="vendor_service")
    assert v["verdict"] == rt.VERDICT_INSURABLE


@pytest.mark.parametrize("direction", ["unclear", "", None, "sideways"])
def test_unknown_direction_degrades_to_review(direction):
    """Without knowing who indemnifies whom, we don't know whose exposure it is."""
    v = rt.assess_indemnity(_ind(direction=direction), project_state="NY",
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_REVIEW
    assert "who indemnifies whom" in v["basis"]


def test_mutual_direction_is_still_assessed():
    v = rt.assess_indemnity(_ind(direction="mutual"), project_state="NY",
                            contract_type="construction")
    assert v["verdict"] == rt.VERDICT_VOID


def test_favorable_direction_wins_over_a_contradictory_form():
    """If the counterparty indemnifies us, a garbled form flag is irrelevant."""
    v = rt.assess_indemnity(_ind(direction="they_indemnify_us", form="limited",
                                 covers_sole_negligence=True),
                            project_state="NY", contract_type="construction")
    assert v["verdict"] == rt.VERDICT_INSURABLE


@pytest.mark.parametrize("form", ["intermediate", "limited"])
def test_contradictory_sole_negligence_flag_degrades_to_review(form):
    """Only broad form reaches sole negligence. A non-broad form carrying the
    flag is a contradictory extraction — it must not pick the alarming branch."""
    v = rt.assess_indemnity(_ind(form=form, covers_sole_negligence=True),
                            project_state="GA", contract_type="construction")
    assert v["verdict"] == rt.VERDICT_REVIEW
    assert "contradictory" in v["basis"]


# --- provisional is about AI extraction, not about confirmation alone --------

def test_manual_contracts_are_never_provisional():
    """A human keyed these terms — there is nothing 'extracted' to confirm."""
    c = _contract(status="manual", ai_available=False, confirmed_at=None)
    review = rt.review_contract(c, [], headcount=10)
    assert review["provisional"] is False
    assert not any("Confirm the extracted terms" in a for a in review["actions"])


def test_ai_parsed_unconfirmed_contract_is_provisional():
    c = _contract(status="parsed", ai_available=True, confirmed_at=None)
    assert rt.review_contract(c, [], headcount=10)["provisional"] is True


def test_is_provisional_predicate():
    assert rt.is_provisional({"ai_available": True, "confirmed_at": None}) is True
    assert rt.is_provisional({"ai_available": True, "confirmed_at": "2026-07-09"}) is False
    assert rt.is_provisional({"ai_available": False, "confirmed_at": None}) is False


# --- enum vocabulary is derived, never hand-synced ---------------------------

def test_enum_lists_track_the_pydantic_literals():
    from typing import get_args
    from app.matcha.models import limit_adequacy as m

    assert rt.CONTRACT_TYPES == list(get_args(m.ContractType))
    assert rt.INDEMNITY_FORMS == list(get_args(m.IndemnityForm))
    assert rt.INDEMNITY_DIRECTIONS == list(get_args(m.IndemnityDirection))


# --- PATCH semantics: exclude_unset + value-compare ---------------------------
#
# `ContractUpdate` (not a stub) — `model_fields_set` IS the mechanism under test,
# and a hand-rolled body with every attribute present cannot exercise it.

class _UpdateConn:
    """Captures the generated UPDATE. `sets` is the SET clause, `args` its binds."""

    def __init__(self, stored=None):
        self.stored = stored or {
            "id": "c1", "requirements": "[]", "risk_transfer": None,
            "contract_type": "construction", "governing_state": "NY", "project_state": "NY",
            "name": "Acme Subcontract", "counterparty": "Acme",
        }
        self.sql = None
        self.args = None

    async def fetchrow(self, sql, *args):
        if sql.strip().startswith("SELECT"):
            return dict(self.stored)
        self.sql, self.args = sql, args
        return dict(self.stored)

    @property
    def reset(self) -> bool:
        return "confirmed_at = NULL" in (self.sql or "")

    def bound(self, col: str):
        """The value bound to `col` in the generated SET clause."""
        import re
        m = re.search(rf"\b{col} = \$(\d+)", self.sql)
        assert m, f"{col} not in SET clause: {self.sql}"
        return self.args[int(m.group(1)) - 1]

    def touched(self, col: str) -> bool:
        import re
        return bool(re.search(rf"\b{col} = \$\d+", self.sql or ""))


def _update(body, stored=None) -> _UpdateConn:
    import asyncio
    conn = _UpdateConn(stored)
    asyncio.run(rt.update_contract(conn, "co", "c1", body))
    return conn


def _body(**kw):
    from app.matcha.models.limit_adequacy import ContractUpdate
    return ContractUpdate(**kw)


@pytest.mark.parametrize("body,expect_reset", [
    # cosmetic edits never disturb the confirmation
    (_body(name="renamed"), False),
    (_body(counterparty="Acme II"), False),
    (_body(requirements=[]), False),
    # re-sending an UNCHANGED verdict input is not an edit. The contract editor
    # posts every field on save, so a null-check here would un-confirm on rename.
    (_body(name="renamed", contract_type="construction"), False),
    (_body(governing_state="NY", project_state="NY"), False),
    # genuinely changing one does un-confirm
    (_body(project_state="CA"), True),
    (_body(governing_state="DE"), True),
    (_body(contract_type="lease"), True),
    # clearing one is a change too
    (_body(project_state=None), True),
])
def test_update_resets_confirmation_only_when_a_verdict_input_changes(body, expect_reset):
    """The verdict is a function of clause AND state AND type — confirming it
    vouches for all three, so *changing* any of them must un-confirm. Re-sending
    the same value must not."""
    assert _update(body).reset is expect_reset


def test_unsent_fields_are_left_alone():
    """`COALESCE(null, col)` semantics are gone: absence means 'don't touch'."""
    conn = _update(_body(name="renamed"))
    assert conn.touched("name")
    for col in ("project_state", "governing_state", "contract_type", "risk_transfer", "requirements"):
        assert not conn.touched(col), col


def test_an_explicit_null_clears_a_verdict_input():
    """A mis-extracted project state must be removable, not merely overwritable —
    it is the single load-bearing input for every construction verdict."""
    conn = _update(_body(project_state=None))
    assert conn.touched("project_state")
    assert conn.bound("project_state") is None
    assert conn.reset is True


def test_states_are_normalized_on_write():
    """A value `_norm_state` would reject must not persist only to read back as
    'unmapped' at verdict time."""
    conn = _update(_body(governing_state="ca"))
    assert conn.bound("governing_state") == "CA"
    assert _update(_body(project_state="1a")).bound("project_state") is None


def test_update_resets_confirmation_when_risk_transfer_changes():
    from app.matcha.models.limit_adequacy import Indemnity, RiskTransfer

    body = _body(risk_transfer=RiskTransfer(indemnity=Indemnity(present=True, form="broad")))
    assert _update(body).reset is True


def test_resending_an_identical_risk_transfer_does_not_reset():
    from app.matcha.models.limit_adequacy import Indemnity, RiskTransfer

    clause = RiskTransfer(indemnity=Indemnity(present=True, form="broad"))
    stored = dict(_UpdateConn().stored, risk_transfer=json.dumps(clause.model_dump()))
    assert _update(_body(risk_transfer=clause), stored).reset is False


def test_update_returns_none_when_the_row_vanishes_mid_update():
    """Deleted between the existence check and the UPDATE → 404, not a 500 on
    `dict(None)`."""
    import asyncio

    class _Racing(_UpdateConn):
        async def fetchrow(self, sql, *args):
            return dict(self.stored) if sql.strip().startswith("SELECT") else None

    assert asyncio.run(rt.update_contract(_Racing(), "co", "c1", _body(name="x"))) is None


def test_an_explicit_null_name_is_ignored_not_written():
    """`name` is NOT NULL in the schema — null means 'don't touch', or the
    UPDATE dies on the constraint."""
    conn = _update(_body(name=None, counterparty="Acme II"))
    assert not conn.touched("name")
    assert conn.touched("counterparty")


def test_update_with_an_empty_body_is_a_no_op():
    conn = _UpdateConn()
    import asyncio
    out = asyncio.run(rt.update_contract(conn, "co", "c1", _body()))
    assert conn.sql is None  # never issued an UPDATE
    assert out["id"] == "c1"


# --- broker submission packet -------------------------------------------------

def _review_with_clause(**over):
    c = {"id": "c1", "name": "Acme Subcontract", "contract_type": "construction",
         "project_state": "NY", "provisional": False, "risk_transfer": _ind(),
         "indemnity": {"verdict": rt.VERDICT_VOID, "statute": "N.Y. Gen. Oblig. Law § 5-322.1"}}
    c.update(over)
    return {"lines": [], "summary": {}, "contracts": [c]}


def test_packet_renders_risk_transfer_even_with_no_limit_rows():
    """A contract can carry a likely-void indemnity while naming no insurance
    limits; a client with no coverage lines must still get that finding."""
    from app.matcha.services import submission_packet as sp

    html = sp._limit_section_html(_review_with_clause())
    assert "Indemnification" in html
    assert "LIKELY VOID" in html
    assert la.DISCLAIMER in html


def test_packet_still_omits_everything_when_there_is_nothing_to_say():
    from app.matcha.services import submission_packet as sp

    assert sp._limit_section_html({"lines": [], "contracts": []}) == ""
    assert sp._limit_section_html(None) == ""


# --- broker pilot corpus ------------------------------------------------------

def test_clause_records_get_their_own_corpus_source_not_the_platform_bucket():
    """The memo appendix dispatches on cid prefix — a `clause:` record inside the
    `platform` bucket would fall through to the native branch and duplicate the
    whole platform table."""
    from app.matcha.services import broker_pilot as bp

    ctx = {"limits": _review_with_clause()}
    corpus = bp.build_corpus("Acme", ctx, docs=[], native=None)

    assert "clause:c1" in corpus["index"]
    assert corpus["index"]["clause:c1"]["source"] == "clauses"
    platform_cids = [r["cid"] for r in corpus["sources"]["platform"]["records"]]
    assert not any(c.startswith("clause:") for c in platform_cids)


def test_clause_record_carries_the_verbatim_quote_and_verdict():
    from app.matcha.services import broker_pilot as bp

    corpus = bp.build_corpus("Acme", {"limits": _review_with_clause()}, docs=[], native=None)
    summary = corpus["index"]["clause:c1"]["summary"]
    assert "Contractor shall indemnify" in summary
    assert "likely void by statute" in summary
    assert "p. 7" in summary


def test_provisional_clause_is_labelled_in_the_corpus():
    from app.matcha.services import broker_pilot as bp

    corpus = bp.build_corpus("Acme", {"limits": _review_with_clause(provisional=True)},
                             docs=[], native=None)
    assert "PROVISIONAL" in corpus["index"]["clause:c1"]["summary"]


def test_no_clauses_source_when_no_contract_has_an_indemnity():
    from app.matcha.services import broker_pilot as bp

    ctx = {"limits": {"contracts": [{"id": "c1", "name": "Bare", "risk_transfer": None}]}}
    corpus = bp.build_corpus("Acme", ctx, docs=[], native=None)
    assert "clauses" not in corpus["sources"]


def test_validate_citations_admits_clause_namespace_and_drops_fakes():
    from app.matcha.services import broker_pilot as bp
    from app.matcha.services.legal_defense import validate_citations

    corpus = bp.build_corpus("Acme", {"limits": _review_with_clause()}, docs=[], native=None)
    clean, dropped = validate_citations(
        [{"point": "p", "cited_ids": ["clause:c1", "clause:bogus"]}], corpus["index"])
    assert clean[0]["cited_ids"] == ["clause:c1"]
    assert dropped == ["clause:bogus"]
