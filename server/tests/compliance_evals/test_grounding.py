"""Grounding suite pure core — value_tokens + evaluate_row + grounding_score.

No DB, no AI: the value-in-cited-text check is deterministic. These lock the
verdict boundaries (real grounding vs recalled number vs stub vs prose).
"""
from datetime import date

from app.core.services.compliance_evals.golden import GoldenFact
from app.core.services.compliance_evals.grounding import (
    CORPUS_STUB, GROUNDED_BUT_WRONG, VALUE_IN_TEXT, VALUE_NOT_IN_TEXT,
    VALUE_UNVERIFIABLE, cross_check_rows, evaluate_row, value_tokens,
)
from app.core.services.compliance_evals.scoring import grounding_score

# A body long enough to clear STUB_BODY_THRESHOLD (500).
LONG = "x" * 600


# ── value_tokens ────────────────────────────────────────────────────────────

def test_tokens_extract_and_normalize_commas():
    assert value_tokens("$844/week ($43,888/year)") == ["844", "43888"]


def test_tokens_include_numeric_value_first():
    assert value_tokens("prose only", numeric_value=7.25)[0] == "7.25"


def test_tokens_strip_citation_references():
    # "29 CFR 1904" / "§ 207" are pointers, not values — must not become tokens.
    assert value_tokens("Record injuries per 29 CFR 1904 Subpart C") == []
    assert value_tokens("1.5x the rate per 29 U.S.C. § 207") == ["1.5"]


def test_tokens_decimal_artifact_trimmed():
    assert value_tokens("40.0 hours") == ["40"]


# ── evaluate_row verdicts ───────────────────────────────────────────────────

def test_value_in_text_digits():
    body = LONG + " the salary is $844 per week which is $43,888 annually"
    res = evaluate_row("$844/week ($43,888/year)", 844, body)
    assert res["verdict"] == VALUE_IN_TEXT and res["missing"] == []


def test_value_in_text_spelled_out_legal_prose():
    # statute says "one and one-half ... forty" not "1.5 ... 40"
    body = LONG + " not less than one and one-half times the regular rate for hours over forty"
    res = evaluate_row("1.5x the regular rate for hours over 40 in a workweek", None, body)
    assert res["verdict"] == VALUE_IN_TEXT, res


def test_value_not_in_text_is_the_critical_case():
    # a real long excerpt, but the asserted number is nowhere in it (recalled).
    body = LONG + " the regular rate applies to hours worked in a workweek"
    res = evaluate_row("$999/week", 999, body)
    assert res["verdict"] == VALUE_NOT_IN_TEXT and "999" in res["missing"]


def test_corpus_stub_short_body():
    res = evaluate_row("$844/week", 844, "Injury and Illness Recordkeeping")  # heading
    assert res["verdict"] == CORPUS_STUB


def test_value_unverifiable_prose_no_number():
    body = LONG + " employers must record work-related injuries and illnesses"
    res = evaluate_row("Record work-related injuries per 29 CFR 1904", None, body)
    # citation digits stripped → no numeric claim → tier-1 can't judge
    assert res["verdict"] == VALUE_UNVERIFIABLE


def test_comma_and_grouping_equivalence():
    body = LONG + " threshold of $43,888 per year"
    assert evaluate_row("43888", 43888, body)["verdict"] == VALUE_IN_TEXT


# ── grounding_score ─────────────────────────────────────────────────────────

def test_score_none_when_nothing_judgeable():
    # all stubs/prose → unmeasured, never 100
    assert grounding_score(0, 0) is None


def test_score_excludes_stubs_from_denominator():
    # 3 verified, 1 contradicted → 75; stubs/prose never entered the call
    assert grounding_score(3, 1) == 75.0


# ── cross_check_rows (tier-2a golden cross-check) ───────────────────────────

def _fact(key, category="wage_hour", comparator="numeric_eq", numeric=None,
          text=None, from_=date(2020, 1, 1), to=None):
    return GoldenFact(
        requirement_key=key, category=category, comparator=comparator,
        expected_numeric=numeric, expected_text=text,
        effective_from=from_, effective_to=to,
        authority_url="https://example.com/law", curated_by="finch",
        curated_at=date(2020, 1, 1),
    )


def _row(key_index, *, id="r1", jid="j1", numeric=None, current="", cat="wage_hour"):
    # a grounded row as cross_check_rows sees it (already indexed elsewhere)
    return {"id": id, "jurisdiction_id": jid, "requirement_key": key_index,
            "category": cat, "numeric_value": numeric, "current_value": current}


def test_cross_check_disagreement_is_critical():
    fact = _fact("minimum_wage", numeric=15.0)
    rows = {"wage_hour:minimum_wage": _row("x:minimum_wage", numeric=12.0)}
    findings, contradicted = cross_check_rows([fact], rows)
    assert contradicted == {"r1"}
    assert len(findings) == 1
    f = findings[0]
    assert f["finding_type"] == GROUNDED_BUT_WRONG and f["severity"] == "critical"
    assert f["expected"]["numeric"] == 15.0


def test_cross_check_agreement_no_finding():
    fact = _fact("minimum_wage", numeric=15.0)
    rows = {"wage_hour:minimum_wage": _row("x:minimum_wage", numeric=15.0)}
    findings, contradicted = cross_check_rows([fact], rows)
    assert findings == [] and contradicted == set()


def test_cross_check_no_matching_grounded_row_skipped():
    # fact has no grounded row → not our concern (golden suite handles absence)
    fact = _fact("minimum_wage", numeric=15.0)
    findings, contradicted = cross_check_rows([fact], {})
    assert findings == [] and contradicted == set()


def test_cross_check_only_active_facts_are_passed_in():
    # caller filters active_on(today); an expired fact simply isn't in the list
    active = []  # expired fact filtered out upstream
    findings, contradicted = cross_check_rows(active, {"wage_hour:minimum_wage": _row("x")})
    assert findings == [] and contradicted == set()
