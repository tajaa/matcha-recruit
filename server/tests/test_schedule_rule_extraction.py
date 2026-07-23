"""Pure-logic tests for schedule-rule catalog extraction (no DB, no network)."""

from app.core.services import schedule_rule_extraction as sre


_ALLOWED = {"req-1", "req-2"}


def _row(**over):
    base = {
        "rule_key": "meal_break_after_hours",
        "rule_value": 5.0,
        "no_rule": False,
        "source_requirement_id": "req-1",
        "citation": "Wash. Rev. Code § 49.12.020",
        "confidence": 0.9,
        "rationale": "meal break after 5 hours",
    }
    base.update(over)
    return base


# ── validate_extraction ──────────────────────────────────────────────────

def test_valid_row_passes():
    valid, rejected = sre.validate_extraction({"rules": [_row()]}, _ALLOWED)
    assert len(valid) == 1 and not rejected
    assert valid[0]["rule_key"] == "meal_break_after_hours"
    assert valid[0]["rule_value"] == 5.0


def test_unknown_rule_key_rejected():
    valid, rejected = sre.validate_extraction({"rules": [_row(rule_key="made_up_key")]}, _ALLOWED)
    assert not valid
    assert rejected[0]["reason"] == "unknown_rule_key"


def test_hallucinated_source_id_rejected():
    valid, rejected = sre.validate_extraction(
        {"rules": [_row(source_requirement_id="not-in-catalog")]}, _ALLOWED,
    )
    assert not valid
    assert rejected[0]["reason"] == "unverifiable_source_requirement_id"


def test_missing_citation_rejected():
    valid, rejected = sre.validate_extraction({"rules": [_row(citation="")]}, _ALLOWED)
    assert not valid
    assert rejected[0]["reason"] == "missing_citation"


def test_no_rule_and_value_both_set_rejected():
    valid, rejected = sre.validate_extraction(
        {"rules": [_row(no_rule=True, rule_value=5.0)]}, _ALLOWED,
    )
    assert not valid
    assert rejected[0]["reason"] == "no_rule_and_value_both_set"


def test_no_value_and_not_no_rule_rejected():
    valid, rejected = sre.validate_extraction(
        {"rules": [_row(rule_value=None, no_rule=False)]}, _ALLOWED,
    )
    assert not valid
    assert rejected[0]["reason"] == "no_value_and_not_no_rule"


def test_valid_no_rule_row():
    valid, rejected = sre.validate_extraction(
        {"rules": [_row(rule_key="minor_16_17_day_hours", rule_value=None, no_rule=True)]}, _ALLOWED,
    )
    assert len(valid) == 1 and not rejected
    assert valid[0]["no_rule"] is True
    assert valid[0]["rule_value"] is None


def test_value_out_of_range_rejected():
    # meal_break_after_hours sanity range is (2, 12)
    valid, rejected = sre.validate_extraction({"rules": [_row(rule_value=99.0)]}, _ALLOWED)
    assert not valid
    assert rejected[0]["reason"] == "value_out_of_range"


def test_non_numeric_value_rejected():
    valid, rejected = sre.validate_extraction({"rules": [_row(rule_value="not-a-number")]}, _ALLOWED)
    assert not valid
    assert rejected[0]["reason"] == "non_numeric_value"


def test_non_object_row_rejected():
    valid, rejected = sre.validate_extraction({"rules": ["just a string"]}, _ALLOWED)
    assert not valid
    assert rejected[0]["reason"] == "not_an_object"


def test_empty_and_junk_payload_tolerated():
    assert sre.validate_extraction({}, _ALLOWED) == ([], [])
    assert sre.validate_extraction({"rules": []}, _ALLOWED) == ([], [])
    assert sre.validate_extraction(None, _ALLOWED) == ([], [])


def test_multiple_rows_mixed_validity():
    payload = {"rules": [_row(), _row(rule_key="bogus"), _row(source_requirement_id="req-2")]}
    valid, rejected = sre.validate_extraction(payload, _ALLOWED)
    assert len(valid) == 2
    assert len(rejected) == 1


# ── decide_upsert ─────────────────────────────────────────────────────────

def test_decide_upsert_no_existing_row_inserts():
    assert sre.decide_upsert(None, _row())["action"] == "insert"


def test_decide_upsert_pending_overwrites():
    existing = {"review_status": "pending", "rule_value": 4.0, "no_rule": False, "citation": "old"}
    assert sre.decide_upsert(existing, _row())["action"] == "overwrite_pending"


def test_decide_upsert_rejected_overwrites():
    existing = {"review_status": "rejected", "rule_value": 4.0, "no_rule": False, "citation": "old"}
    assert sre.decide_upsert(existing, _row())["action"] == "overwrite_pending"


def test_decide_upsert_approved_matching_is_noop():
    existing = {"review_status": "approved", "rule_value": 5.0, "no_rule": False, "citation": _row()["citation"]}
    assert sre.decide_upsert(existing, _row())["action"] == "noop"


def test_decide_upsert_approved_drift_sets_proposed():
    existing = {"review_status": "approved", "rule_value": 6.0, "no_rule": False, "citation": "different"}
    assert sre.decide_upsert(existing, _row())["action"] == "set_proposed"


# ── registry sanity ────────────────────────────────────────────────────────

def test_every_range_key_has_a_rule_key():
    assert set(sre._RANGES) == set(sre.RULE_KEYS)


def test_sick_leave_not_in_extraction_categories():
    # No evaluator enforces a sick-leave threshold — extracting it would
    # create approved rows nothing reads.
    assert "sick_leave" not in sre.CATALOG_CATEGORIES


def test_code_curated_states_are_skipped():
    assert set(sre.CODE_CURATED_STATES) == {"US", "CA"}
