"""Pure-function tests for the agentic Compliance Pilot's loop helpers (no
DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/compliance_pilot -q

Covers `_cap_payload` truncation, `_StepRecorder` args capture, `is_sole_finish`
(a batched `finish` must be deferred), `_to_contents` history shaping, and the
list_actions/uncodified_backlog result-shaping helpers (`_compact_result`,
`_action_overview`, `_backlog_item`).
"""

from app.core.services.compliance_pilot.agent import (
    _MAX_MESSAGE_CHARS,
    _STEP_PAYLOAD_CAP_CHARS,
    _StepRecorder,
    _action_overview,
    _backlog_item,
    _cap_payload,
    _compact_result,
    _to_contents,
    is_sole_finish,
)

A = "1e2b3c4d-5678-4abc-9def-0123456789ab"


# --------------------------------------------------------------------------- #
# _cap_payload
# --------------------------------------------------------------------------- #

class TestCapPayload:
    def test_small_value_unchanged(self):
        value = {"a": 1, "b": "hello"}
        assert _cap_payload(value) == value

    def test_none_stays_none(self):
        assert _cap_payload(None) is None

    def test_oversized_value_truncated(self):
        value = {"blob": "x" * (_STEP_PAYLOAD_CAP_CHARS + 500)}
        capped = _cap_payload(value)
        assert capped["_truncated"] is True
        assert len(capped["preview"]) <= _STEP_PAYLOAD_CAP_CHARS

    def test_uuid_and_date_become_json_safe(self):
        from datetime import date
        from uuid import UUID
        value = {"id": UUID(A), "day": date(2026, 7, 27)}
        capped = _cap_payload(value)
        assert capped == {"id": A, "day": "2026-07-27"}


# --------------------------------------------------------------------------- #
# _StepRecorder
# --------------------------------------------------------------------------- #

class TestStepRecorder:
    def test_record_captures_args(self):
        recorder = _StepRecorder()
        step = recorder.record(tool="coverage_snapshot", kind="read", label="Checked CA", status="ok",
                               args={"state": "CA"})
        assert step["args"] == {"state": "CA"}
        assert step["seq"] == 1

    def test_record_without_args_omits_key(self):
        recorder = _StepRecorder()
        step = recorder.record(tool="finish", kind="finish", label="Done", status="ok")
        assert "args" not in step

    def test_seq_is_monotonic(self):
        recorder = _StepRecorder()
        s1 = recorder.record(tool="a", kind="read", label="A", status="ok")
        s2 = recorder.record(tool="b", kind="read", label="B", status="ok")
        assert s1["seq"] == 1 and s2["seq"] == 2


# --------------------------------------------------------------------------- #
# is_sole_finish
# --------------------------------------------------------------------------- #

def test_sole_finish_true_only_when_finish_is_alone():
    assert is_sole_finish(["finish"]) is True
    assert is_sole_finish(["stage_research", "finish"]) is False
    assert is_sole_finish(["finish", "stage_research"]) is False
    assert is_sole_finish([]) is False
    assert is_sole_finish(["stage_research"]) is False


# --------------------------------------------------------------------------- #
# _to_contents
# --------------------------------------------------------------------------- #

def test_to_contents_maps_roles_and_keeps_order():
    history = [
        {"role": "user", "content": "Research CA healthcare"},
        {"role": "assistant", "content": "Staged it."},
    ]
    contents = _to_contents(history)
    assert [c.role for c in contents] == ["user", "model"]
    assert contents[0].parts[0].text == "Research CA healthcare"


def test_to_contents_truncates_long_messages():
    history = [{"role": "user", "content": "x" * (_MAX_MESSAGE_CHARS + 500)}]
    contents = _to_contents(history)
    assert len(contents[0].parts[0].text) <= _MAX_MESSAGE_CHARS + len("\n…[truncated]")
    assert contents[0].parts[0].text.endswith("[truncated]")


def test_to_contents_drops_empty_messages():
    history = [{"role": "user", "content": "   "}, {"role": "user", "content": "real"}]
    contents = _to_contents(history)
    assert len(contents) == 1
    assert contents[0].parts[0].text == "real"


def test_to_contents_falls_back_to_hello_when_history_is_empty():
    contents = _to_contents([])
    assert len(contents) == 1
    assert contents[0].parts[0].text == "Hello."


# --------------------------------------------------------------------------- #
# Result-shaping helpers
# --------------------------------------------------------------------------- #

def test_compact_result_drops_nested_detail_keeps_scalars():
    result = {
        "staged": 18, "codifiable": 12, "state": "CA",
        "staged_rows": [{"id": "x"}] * 18,  # the detail list_actions must NOT carry
    }
    compact = _compact_result(result)
    assert compact == {"staged": 18, "codifiable": 12, "state": "CA"}


def test_compact_result_passes_through_non_dicts():
    assert _compact_result(None) is None
    assert _compact_result("not a dict") == "not a dict"


def test_action_overview_serializes_uuids_and_compacts_result():
    from uuid import UUID
    row = {
        "id": UUID(A), "kind": "research", "status": "done",
        "params": {"state": "CA"}, "progress": None,
        "result": {"staged": 5, "staged_rows": [1, 2, 3]},
        "started_at": None, "finished_at": None,
    }
    out = _action_overview(row)
    assert out["action_id"] == A
    assert out["result"] == {"staged": 5}


def test_backlog_item_projects_the_fields_a_model_needs():
    item = {
        "classification_id": "uuid-1", "regulation_key": "min_wage_general",
        "category_slug": "minimum_wage", "severity": "high", "level": "state",
        "citation": "Cal. Lab. Code § 1197", "heading": "Minimum wage",
        "item_id": "uuid-2", "index_slug": "ca-labor-code", "has_body": True,
    }
    out = _backlog_item(item)
    assert out["regulation_key"] == "min_wage_general"
    assert out["category"] == "minimum_wage"
    assert out["level"] == "state"
    assert "classification_id" not in out  # internal id, not useful to the model
