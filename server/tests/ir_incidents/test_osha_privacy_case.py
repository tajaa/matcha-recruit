"""Unit tests for OSHA Privacy Case determination + clinical description.

Pure-helper tests — no app boot, no DB, no LLM. The determination decides when
the injured employee's name is masked to "Privacy Case" on the 300/301 log; the
clinical-description composer builds the OSHA injury phrase from structured
fields so no narrative (and thus no third-party name) reaches the export.
"""
from app.core.services.osha_privacy import (
    determine_privacy_case,
    compose_clinical_description,
)


# ── the 6 trigger conditions ────────────────────────────────────────────────

def test_intimate_body_part_triggers():
    is_priv, reason = determine_privacy_case({"body_parts": ["groin"]}, "injury", False)
    assert is_priv and reason == "intimate_injury"


def test_sexual_assault_triggers():
    is_priv, reason = determine_privacy_case({"from_sexual_assault": True}, "injury", False)
    assert is_priv and reason == "sexual_assault"


def test_mental_illness_triggers():
    is_priv, reason = determine_privacy_case({}, "mental_illness", False)
    assert is_priv and reason == "mental_illness"


def test_infectious_pathogen_triggers_any_case():
    for agent in ("hiv", "Hepatitis", "TUBERCULOSIS"):
        is_priv, reason = determine_privacy_case({"infectious_agent": agent}, "other_illness", False)
        assert is_priv and reason == "infectious_pathogen"


def test_contaminated_sharps_triggers():
    is_priv, reason = determine_privacy_case({"contaminated_sharps": True}, "injury", False)
    assert is_priv and reason == "contaminated_sharps"


def test_voluntary_opt_out_requires_both_illness_and_request():
    # both true → privacy case
    is_priv, reason = determine_privacy_case({}, "other_illness", True)
    assert is_priv and reason == "voluntary_opt_out"
    # illness but no request → not a privacy case
    assert determine_privacy_case({}, "other_illness", False) == (False, None)
    # request but it's an injury (not an illness) → not a privacy case
    assert determine_privacy_case({}, "injury", True) == (False, None)


# ── non-triggers + precedence ───────────────────────────────────────────────

def test_standard_injury_not_privacy_case():
    out = determine_privacy_case(
        {"body_parts": ["left_hand"], "injury_type": "laceration"}, "injury", False
    )
    assert out == (False, None)


def test_reason_precedence_first_match_wins():
    # multiple conditions true → first in PRIVACY_CASE_REASONS order wins
    cd = {"body_parts": ["groin"], "from_sexual_assault": True, "contaminated_sharps": True}
    is_priv, reason = determine_privacy_case(cd, "mental_illness", True)
    assert is_priv and reason == "intimate_injury"


def test_defensive_against_none_and_missing():
    assert determine_privacy_case(None, None, False) == (False, None)
    # opt-out requested but no illness type present → not a privacy case
    assert determine_privacy_case({}, None, True) == (False, None)


def test_string_valued_signals_coerced():
    # Gemini/JSON may emit string flags; "true"/"yes" trigger, "false" must not
    # (bare bool("false") would be True — the bug _truthy guards against).
    assert determine_privacy_case({"from_sexual_assault": "true"}, "injury", False)[0] is True
    assert determine_privacy_case({"contaminated_sharps": "yes"}, "injury", False)[0] is True
    assert determine_privacy_case({"from_sexual_assault": "false"}, "injury", False) == (False, None)
    # opt-out passed as a string on an illness
    assert determine_privacy_case({}, "other_illness", "true")[0] is True
    assert determine_privacy_case({}, "other_illness", "false") == (False, None)


# ── clinical description: structured only, no name leakage ───────────────────

def test_clinical_description_full():
    out = compose_clinical_description(
        {"injury_type": "laceration", "body_parts": ["left_hand"], "equipment_involved": "needlestick"}
    )
    assert out == "Laceration to left hand from needlestick"


def test_clinical_description_body_only_and_nature_only():
    assert compose_clinical_description({"injury_type": "fracture"}) == "Fracture"
    assert compose_clinical_description({"body_parts": ["right_knee"]}) == "Injury to right knee"


def test_clinical_description_empty_returns_none():
    assert compose_clinical_description({}) is None
    assert compose_clinical_description(None) is None


def test_clinical_description_ignores_narrative_names():
    # A patient name living only in a narrative key must NOT appear — the composer
    # reads ONLY structured injury fields (this is what kills the screenshot leak).
    cd = {
        "injury_type": "bite",
        "body_parts": ["arm"],
        "description": "I was tending to Julianna when she bit me",  # narrative — ignored
        "narrative": "helping Simon",
    }
    out = compose_clinical_description(cd)
    assert "Julianna" not in out and "Simon" not in out
    assert out == "Bite to arm"
