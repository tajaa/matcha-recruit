"""Pure-logic tests for schedule-rule catalog extraction (no DB, no network)."""

from unittest.mock import AsyncMock

import pytest

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


# ── cross-row: the meal window has to be a window ─────────────────────────

def _earliest(value):
    return _row(rule_key="meal_break_earliest_after_hours", rule_value=value)


def test_earliest_at_or_past_the_deadline_is_rejected():
    """Each bound is in range on its own; together they hold no break."""
    for earliest in (5.0, 6.0):
        payload = {"rules": [_row(rule_value=5.0), _earliest(earliest)]}
        valid, rejected = sre.validate_extraction(payload, _ALLOWED)
        assert [row["rule_key"] for row in valid] == ["meal_break_after_hours"]
        assert [row["reason"] for row in rejected] == ["earliest_not_before_deadline"]


def test_earliest_before_the_deadline_is_kept():
    payload = {"rules": [_row(rule_value=5.0), _earliest(2.0)]}
    valid, rejected = sre.validate_extraction(payload, _ALLOWED)
    assert len(valid) == 2 and not rejected


def test_earliest_is_kept_when_the_run_carries_no_deadline():
    # The pair can be approved out of separate runs; the adaptation layer in
    # schedule_break_rule_store is the backstop for that, not this check.
    valid, rejected = sre.validate_extraction({"rules": [_earliest(6.0)]}, _ALLOWED)
    assert len(valid) == 1 and not rejected


def test_a_state_with_no_meal_rule_at_all_keeps_its_no_rule_rows():
    payload = {
        "rules": [
            _row(rule_value=None, no_rule=True),
            _earliest(None) | {"no_rule": True},
        ],
    }
    valid, rejected = sre.validate_extraction(payload, _ALLOWED)
    assert len(valid) == 2 and not rejected


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


def test_every_rule_key_is_explained_to_the_model():
    # A key the glossary never describes gets extracted by guesswork.
    for key in sre.RULE_KEYS:
        assert key in sre._FIELD_GLOSSARY, key


def test_meal_break_earliest_is_extractable():
    """WA/OR legislate how EARLY a meal may start; break suggestions read it."""
    assert "meal_break_earliest_after_hours" in sre.RULE_KEYS
    assert sre._RANGES["meal_break_earliest_after_hours"] == (0.5, 6)


def test_sick_leave_not_in_extraction_categories():
    # No evaluator enforces a sick-leave threshold — extracting it would
    # create approved rows nothing reads.
    assert "sick_leave" not in sre.CATALOG_CATEGORIES


def test_code_curated_states_are_skipped():
    assert set(sre.CODE_CURATED_STATES) == {"US", "CA", "NY"}


# --- Model routing (platform "Agent model" setting) ---------------------------

class _ExtractionConn:
    """Answers the run-row insert, returns one catalog row, records writes."""

    def __init__(self):
        self.inserted_model = None
        self.executed = []

    async def fetchval(self, query, *args):
        self.inserted_model = args[1]
        return "run-1"

    async def fetch(self, query, *args):
        return [{"id": "req-1", "requirement_key": "meal_break", "category": "meal_breaks",
                 "title": "Meal break", "description": "30 min after 5h", "current_value": "30",
                 "numeric_value": 30, "statute_citation": "Example Code 1"}]

    async def execute(self, query, *args):
        self.executed.append((query, args))


@pytest.mark.asyncio
async def test_extraction_runs_on_claude_when_the_setting_picks_it(monkeypatch):
    generate = AsyncMock(return_value='```json\n{"rules": []}\n```')
    monkeypatch.setattr(sre.anthropic_messages, "claude_override", AsyncMock(return_value="claude-sonnet-5-5"))
    monkeypatch.setattr(sre.anthropic_messages, "generate_text", generate)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    conn = _ExtractionConn()

    out = await sre.extract_state_rules(conn, "wa")

    assert out == {"status": "complete", "requirement_count": 1, "extracted_count": 0, "rejected_count": 0}
    assert conn.inserted_model == "claude-sonnet-5-5"  # the run row records what ran
    assert generate.await_args.kwargs["model"] == "claude-sonnet-5-5"
    assert generate.await_args.kwargs["json_output"] is True
    assert "WA" in generate.await_args.args[0]


@pytest.mark.asyncio
async def test_a_claude_failure_marks_the_run_failed(monkeypatch):
    monkeypatch.setattr(sre.anthropic_messages, "claude_override", AsyncMock(return_value="claude-haiku-5-5"))
    monkeypatch.setattr(sre.anthropic_messages, "generate_text", AsyncMock(side_effect=RuntimeError("boom")))
    conn = _ExtractionConn()

    out = await sre.extract_state_rules(conn, "WA")

    assert out["status"] == "failed"
    assert any("status = 'failed'" in query for query, _ in conn.executed)


@pytest.mark.asyncio
async def test_default_setting_keeps_gemini(monkeypatch):
    generate = AsyncMock()
    monkeypatch.setattr(sre.anthropic_messages, "claude_override", AsyncMock(return_value=None))
    monkeypatch.setattr(sre.anthropic_messages, "generate_text", generate)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    conn = _ExtractionConn()

    out = await sre.extract_state_rules(conn, "WA")

    # No Gemini key in the test process: the Gemini path fails as before, and
    # Claude was never asked.
    assert out["status"] == "failed" and conn.inserted_model == sre._MODEL
    generate.assert_not_awaited()
