"""Unit tests for OSHA Privacy Case determination + clinical description.

Pure-helper tests — no app boot, no DB, no LLM. The determination decides when
the injured employee's name is masked to "Privacy Case" on the 300/301 log; the
clinical-description composer builds the OSHA injury phrase from structured
fields so no narrative (and thus no third-party name) reaches the export.
"""
from app.core.services.osha_privacy import (
    determine_privacy_case,
    compose_clinical_description,
    PRIVACY_DESCRIPTION_PLACEHOLDER,
)
from app.matcha.routes.ir_incidents._shared import _privacy_signal_overlay
from app.matcha.routes.ir_incidents.osha import (
    _resolve_privacy_mask,
    _resolve_osha_description,
    _injured_persons,
)


# ── the 6 trigger conditions ────────────────────────────────────────────────

def test_intimate_body_part_triggers():
    is_priv, reason = determine_privacy_case({"body_parts": ["groin"]}, "injury", False)
    assert is_priv and reason == "intimate_injury"


def test_intimate_injury_flag_triggers():
    # Explicit flag (manual checkbox / AI extraction), independent of body_parts.
    assert determine_privacy_case({"intimate_injury": True}, "injury", False) == (True, "intimate_injury")
    assert determine_privacy_case({"intimate_injury": "true"}, "injury", False) == (True, "intimate_injury")
    assert determine_privacy_case({"intimate_injury": False}, "injury", False) == (False, None)


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


def test_privacy_signal_overlay_positive_only():
    # AI extraction → only meaningful/positive keys are written (no false/none
    # defaults that would block a later human override or falsely mask).
    out = _privacy_signal_overlay({
        "injury_type": "Laceration",
        "body_parts": ["Groin"],
        "intimate_injury": True,
        "from_sexual_assault": False,
        "infectious_agent": "hiv",
        "contaminated_sharps": False,
    })
    assert out == {
        "injury_type": "laceration",
        "body_parts": ["groin"],
        "intimate_injury": True,
        "infectious_agent": "hiv",
    }


def test_privacy_signal_overlay_empty_when_nothing_positive():
    assert _privacy_signal_overlay({"intimate_injury": False, "infectious_agent": "none"}) == {}
    assert _privacy_signal_overlay({}) == {}
    assert _privacy_signal_overlay(None) == {}


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


# ── hybrid per-employee name masking (Column B) ──────────────────────────────

def test_privacy_mask_human_reason_wins():
    cd = {"privacy_cases": {"emp1": "mental_illness"}}
    assert _resolve_privacy_mask(cd, {}, "emp1") == (True, "mental_illness")


def test_privacy_mask_human_none_blocks_safety_net():
    # body_parts would auto-trigger intimate_injury, but the human reviewed this
    # employee and explicitly cleared it → must NOT mask.
    cd = {"privacy_cases": {"emp1": "none"}, "body_parts": ["groin"]}
    assert _resolve_privacy_mask(cd, {}, "emp1") == (False, None)


def test_privacy_mask_unanswered_uses_safety_net():
    # No human answer → fall back to determine_privacy_case (incident-level).
    assert _resolve_privacy_mask({"body_parts": ["groin"]}, {}, "emp1") == (True, "intimate_injury")
    # Unanswered + no signal → not masked.
    assert _resolve_privacy_mask({}, {}, "emp1") == (False, None)
    # Safety net also reads the OSHA M-column (mental_illness).
    assert _resolve_privacy_mask({}, {"injury_type": "mental_illness"}, "emp1") == (True, "mental_illness")


def test_privacy_mask_is_per_employee():
    cd = {"privacy_cases": {"empA": "sexual_assault", "empB": "none"}}
    assert _resolve_privacy_mask(cd, {}, "empA") == (True, "sexual_assault")
    assert _resolve_privacy_mask(cd, {}, "empB") == (False, None)
    # empC has no answer and no signal → safety net says not a privacy case.
    assert _resolve_privacy_mask(cd, {}, "empC") == (False, None)


def test_privacy_mask_reason_case_insensitive():
    assert _resolve_privacy_mask({"privacy_cases": {"e": "Mental_Illness"}}, {}, "e") == (True, "mental_illness")


# ── Column F description precedence (never the raw narrative) ─────────────────

def test_description_prefers_ai_cleansed():
    cd = {
        "osha_clean_description": "Employee lacerated left hand on a needle.",
        "injury_type": "laceration", "body_parts": ["left_hand"],
    }
    assert _resolve_osha_description(cd, False) == "Employee lacerated left hand on a needle."


def test_description_falls_back_to_structured():
    cd = {"injury_type": "laceration", "body_parts": ["left_hand"]}
    assert _resolve_osha_description(cd, False) == "Laceration to left hand"


def test_description_placeholder_when_empty():
    assert _resolve_osha_description({}, True) == PRIVACY_DESCRIPTION_PLACEHOLDER
    assert "incident record" in _resolve_osha_description({}, False).lower()


def test_description_never_uses_raw_narrative():
    # Narrative keys holding names must NEVER surface — only structured/clean fields.
    cd = {
        "description": "I was tending to Julianna when Simon bit me",  # ignored
        "narrative": "Simon",  # ignored
        "injury_type": "bite", "body_parts": ["arm"],
    }
    out = _resolve_osha_description(cd, False)
    assert "Julianna" not in out and "Simon" not in out
    assert out == "Bite to arm"


# ── one row per injured employee ─────────────────────────────────────────────

def test_injured_persons_roster_split():
    a, b = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    row = {"involved_employee_ids": [a, b], "reported_by_name": "Reporter"}
    emp_map = {
        a: {"first_name": "Alice", "last_name": "Stone", "job_title": "Nurse"},
        b: {"first_name": "Bob", "last_name": "Reed", "job_title": "Tech"},
    }
    assert _injured_persons(row, emp_map) == [
        (a, "Alice Stone", "Nurse"),
        (b, "Bob Reed", "Tech"),
    ]


def test_injured_persons_missing_roster_id_is_mask_safe():
    eid = "33333333-3333-3333-3333-333333333333"
    row = {"involved_employee_ids": [eid], "reported_by_name": "Reporter"}
    # Unresolvable id still yields a row, never a leaked name.
    assert _injured_persons(row, {}) == [(eid, "Unknown", None)]


def test_injured_persons_reporter_fallback_no_roster():
    # No roster ids → single reporter row keyed "reporter".
    row = {"involved_employee_ids": [], "reported_by_name": "Dana Fields",
           "emp_first_name": None, "emp_last_name": None, "emp_job_title": None}
    assert _injured_persons(row, {}) == [("reporter", "Dana Fields", None)]
    # Reporter matched to the roster → use the joined name + Finch title.
    row2 = {"involved_employee_ids": [], "reported_by_name": "Dana Fields",
            "emp_first_name": "Dana", "emp_last_name": "Fields", "emp_job_title": "Aide"}
    assert _injured_persons(row2, {}) == [("reporter", "Dana Fields", "Aide")]
