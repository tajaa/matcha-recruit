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
    _mask_from_reason,
    _resolve_osha_description,
    _injured_persons,
    _osha_case_views,
    _attest_export,
    EXPORT_DISCLAIMER,
)
import asyncio
import json
from types import SimpleNamespace
import pytest
from fastapi import HTTPException


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


# ── hybrid Column-B mask from a case's privacy answer ────────────────────────

def test_mask_human_reason_wins():
    assert _mask_from_reason("mental_illness", {}, None) == (True, "mental_illness")


def test_mask_human_none_blocks_safety_net():
    # body_parts would auto-trigger intimate_injury, but the human explicitly
    # cleared this case ("none") → must NOT mask.
    assert _mask_from_reason("none", {"body_parts": ["groin"]}, None) == (False, None)


def test_mask_unanswered_uses_safety_net():
    # No answer → determine_privacy_case (incident signals + this case's M-column).
    assert _mask_from_reason(None, {"body_parts": ["groin"]}, None) == (True, "intimate_injury")
    assert _mask_from_reason(None, {}, None) == (False, None)
    assert _mask_from_reason(None, {}, "mental_illness") == (True, "mental_illness")


def test_mask_reason_case_insensitive():
    assert _mask_from_reason("Mental_Illness", {}, None) == (True, "mental_illness")


# ── per-injured-employee case views (300/301 reads) ──────────────────────────

def test_osha_case_views_from_case_rows():
    a = "11111111-1111-1111-1111-111111111111"
    row = {"id": "inc1", "category_data": {}, "osha_form_301_data": {},
           "involved_employee_ids": [a], "reported_by_name": "Rep"}
    case_rows = [{
        "case_key": a, "case_seq": 1, "employee_id": a,
        "classification": "days_away", "days_away": 5, "days_restricted": 0,
        "injury_type": "injury", "privacy_case_reason": "mental_illness",
    }]
    emp_map = {a: {"first_name": "Alice", "last_name": "Stone", "job_title": "Nurse"}}
    (v,) = _osha_case_views(row, case_rows, emp_map)
    assert v["name"] == "Alice Stone" and v["job_title"] == "Nurse"
    assert v["classification"] == "days_away" and v["days_away"] == 5
    assert v["injury_type"] == "injury" and v["privacy_case_reason"] == "mental_illness"


def test_osha_case_views_fallback_to_incident_level():
    # No case rows yet → synthesize from incident-level columns + privacy_cases.
    a = "22222222-2222-2222-2222-222222222222"
    row = {"id": "inc2",
           "category_data": {"privacy_cases": {a: "sexual_assault"}},
           "osha_form_301_data": {"injury_type": "injury"},
           "involved_employee_ids": [a], "reported_by_name": "Rep",
           "osha_classification": "restricted_duty",
           "days_away_from_work": 0, "days_restricted_duty": 3}
    emp_map = {a: {"first_name": "Bob", "last_name": "Reed", "job_title": "Tech"}}
    (v,) = _osha_case_views(row, [], emp_map)
    assert v["name"] == "Bob Reed" and v["classification"] == "restricted_duty"
    assert v["days_restricted"] == 3 and v["injury_type"] == "injury"
    assert v["privacy_case_reason"] == "sexual_assault"


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


# ── pre-export reviewer attestation gate ─────────────────────────────────────

class _FakeUser:
    id = "user-123"


class _FakeConn:
    """Captures log_audit's INSERT so the attested path can be asserted."""
    def __init__(self):
        self.calls = []

    async def execute(self, query, *args):
        self.calls.append((query, args))


def test_export_attestation_required_blocks_without_ack():
    # No acknowledgement → 403 carrying the disclaimer; no audit write attempted.
    conn = _FakeConn()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_attest_export(conn, _FakeUser(), form="300_log", year=2026, attested=False))
    assert ei.value.status_code == 403
    assert ei.value.detail["code"] == "attestation_required"
    assert EXPORT_DISCLAIMER == ei.value.detail["disclaimer"]
    assert conn.calls == []  # nothing logged when blocked


def test_export_attestation_records_audit_when_acknowledged():
    # Acknowledged → one osha_export_attested audit row (who / form / year / loc).
    conn = _FakeConn()
    asyncio.run(_attest_export(
        conn, _FakeUser(), form="ita", year=2026, attested=True, location_id="loc-9",
    ))
    assert len(conn.calls) == 1
    query, args = conn.calls[0]
    assert "ir_audit_log" in query
    # log_audit positional order: incident_id, user_id, action, entity_type, entity_id, details_json, ip
    assert args[1] == "user-123"
    assert args[2] == "osha_export_attested"
    assert args[3] == "osha_export"
    assert args[4] == "loc-9"
    details = json.loads(args[5])
    assert details["form"] == "ita" and details["year"] == 2026


def test_injured_persons_reporter_fallback_no_roster():
    # No roster ids → single reporter row keyed "reporter".
    row = {"involved_employee_ids": [], "reported_by_name": "Dana Fields",
           "emp_first_name": None, "emp_last_name": None, "emp_job_title": None}
    assert _injured_persons(row, {}) == [("reporter", "Dana Fields", None)]
    # Reporter matched to the roster → use the joined name + Finch title.
    row2 = {"involved_employee_ids": [], "reported_by_name": "Dana Fields",
            "emp_first_name": "Dana", "emp_last_name": "Fields", "emp_job_title": "Aide"}
    assert _injured_persons(row2, {}) == [("reporter", "Dana Fields", "Aide")]


# ── human-approved OSHA description (Column F) review card ────────────────────

def test_build_osha_clean_description_card_shape():
    from app.matcha.routes.ir_incidents._shared import build_osha_clean_description_card
    card = build_osha_clean_description_card("An employee slipped and fell in the warehouse.")
    assert card["id"] == "osha_clean_description_review"
    a = card["action"]
    assert a["type"] == "text_input"               # reuses the existing text_input renderer
    assert a["target_field"] == "osha_clean_description"
    assert a["label"] == "Approve"
    assert a["prefilled"] == "An employee slipped and fell in the warehouse."


def test_build_osha_clean_description_card_raw_fallback_copy():
    # cleansed=False (AI unavailable) seeds the raw narrative and tells the
    # human to strip names — distinct copy from the approve-as-written default.
    from app.matcha.routes.ir_incidents._shared import build_osha_clean_description_card
    clean = build_osha_clean_description_card("An employee slipped.", cleansed=True)
    raw = build_osha_clean_description_card("John slipped and fell.", cleansed=False)
    assert raw["action"]["prefilled"] == "John slipped and fell."
    # default copy claims names already removed; fallback asks the human to do it
    assert "removed every person's name" in clean["recommendation"]
    assert "removed every person's name" not in raw["recommendation"]
    assert "names no one" in raw["recommendation"] or "strip" in raw["recommendation"].lower()


def test_osha_description_approval_writes_and_advances(monkeypatch):
    # Approving the review card writes the canonical osha_clean_description +
    # the osha_description_approved gate, then resumes the per-case loop.
    import app.matcha.routes.ir_incidents.copilot as cp

    captured = {}

    class FakeConn:
        async def execute(self, query, *args):
            captured["execute"] = (query, args)

    async def fake_next_case_step(conn, incident_id):
        return None  # no case rows in this unit context → no follow-on card

    monkeypatch.setattr(cp, "next_case_step", fake_next_case_step)

    res = asyncio.run(cp._handle_text_input(
        FakeConn(),
        incident_id="inc-1",
        action={"target_field": "osha_clean_description"},
        body=SimpleNamespace(text_value="  An employee slipped and fell in the warehouse.  "),
        current_user=SimpleNamespace(id="u1"),
    ))
    assert res["event_summary"] == "OSHA 300 description approved"
    assert res["event_extra"]["new_value"] == "An employee slipped and fell in the warehouse."
    query, args = captured["execute"]
    assert "osha_clean_description" in query and "osha_description_approved" in query
    assert args[0] == "An employee slipped and fell in the warehouse."  # trimmed, names already gone


def test_osha_description_review_skips_when_already_approved():
    # Idempotent gate: once approved, the review card is never re-emitted and no
    # cleanse/write is attempted.
    import app.matcha.routes.ir_incidents.copilot as cp

    class FakeConn:
        async def fetchval(self, query, *args):
            return json.dumps({"osha_description_approved": True})

        async def execute(self, *a, **k):
            raise AssertionError("must not write when already approved")

    res = asyncio.run(cp._emit_osha_description_review(
        FakeConn(), "inc-1", SimpleNamespace(id="u1"),
    ))
    assert res is None


def test_osha_description_approval_rejects_empty():
    import app.matcha.routes.ir_incidents.copilot as cp

    class FakeConn:  # must never be touched on the empty path
        async def execute(self, *a, **k):
            raise AssertionError("must not write on empty approval")

    res = asyncio.run(cp._handle_text_input(
        FakeConn(),
        incident_id="inc-1",
        action={"target_field": "osha_clean_description"},
        body=SimpleNamespace(text_value="   "),
        current_user=SimpleNamespace(id="u1"),
    ))
    assert "error" in res
