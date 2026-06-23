"""Pure-logic tests for the IR voice-parse field coercer.

No network / no DB — only _coerce_voice_fields (the validate/clamp step that turns
Gemini's raw JSON into a safe create-form prefill). The Gemini audio call itself is
exercised by a manual dev mic smoke.
"""

from app.matcha.services.ir_voice_parser import _coerce_voice_fields, MAX_WITNESSES

LOCS = {"11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"}
TYPES = {"safety", "behavioral", "property", "near_miss", "other"}
SEV = {"critical", "high", "medium", "low"}


def _coerce(raw):
    return _coerce_voice_fields(raw, LOCS, TYPES, SEV)


def test_empty_payload_all_null():
    f = _coerce({})
    assert f["transcript"] is None and f["description"] is None
    assert f["reported_by_name"] is None and f["occurred_at_text"] is None
    assert f["witnesses"] == []
    assert f["location_id"] is None and f["incident_type"] is None and f["severity"] is None


def test_valid_location_passes_invalid_dropped():
    good = "11111111-1111-1111-1111-111111111111"
    assert _coerce({"location_id": good})["location_id"] == good
    assert _coerce({"location_id": "99999999-9999-9999-9999-999999999999"})["location_id"] is None
    assert _coerce({"location_id": "not-a-uuid"})["location_id"] is None


def test_enums_validated():
    assert _coerce({"incident_type": "safety", "severity": "high"}) | {} and \
        _coerce({"incident_type": "safety"})["incident_type"] == "safety"
    assert _coerce({"incident_type": "Safety"})["incident_type"] is None   # case-sensitive
    assert _coerce({"incident_type": "fire"})["incident_type"] is None
    assert _coerce({"severity": "severe"})["severity"] is None
    assert _coerce({"severity": "low"})["severity"] == "low"


def test_witnesses_normalized_from_mixed_shapes():
    f = _coerce({"witnesses": ["Bob Smith", {"name": "Jane Doe"}, {"name": "  "}, {}, "  ", 5]})
    assert f["witnesses"] == [{"name": "Bob Smith"}, {"name": "Jane Doe"}]


def test_witnesses_capped():
    f = _coerce({"witnesses": [{"name": f"P{i}"} for i in range(MAX_WITNESSES + 10)]})
    assert len(f["witnesses"]) == MAX_WITNESSES


def test_strings_trimmed_and_blank_to_none():
    f = _coerce({"description": "  he slipped  ", "reported_by_name": "   ", "occurred_at_text": "yesterday"})
    assert f["description"] == "he slipped"
    assert f["reported_by_name"] is None
    assert f["occurred_at_text"] == "yesterday"
