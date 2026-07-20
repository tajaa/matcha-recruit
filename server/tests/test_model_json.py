"""Tests for the shared model-JSON parsing helpers.

These pin the behaviours the fifteen scattered copies collectively had, so a
site migrating onto the shared version cannot quietly lose a fixup it relied on.
"""

import json

import pytest

from app.core.services.model_json import (
    clean_model_json,
    parse_model_json,
    strip_json_fence,
)


class TestStripJsonFence:
    def test_strips_json_fence(self):
        assert strip_json_fence('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_bare_fence(self):
        assert strip_json_fence('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_handles_unclosed_fence(self):
        # The model opens a fence and never closes it. A single anchored regex
        # misses this; the prefix/suffix form is why the helper is written that way.
        assert strip_json_fence('```json\n{"a": 1}') == '{"a": 1}'

    def test_leaves_unfenced_text_alone(self):
        assert strip_json_fence('{"a": 1}') == '{"a": 1}'

    def test_empty_and_none(self):
        assert strip_json_fence("") == ""
        assert strip_json_fence(None) == ""


class TestCleanModelJson:
    def test_narrows_to_object_inside_prose(self):
        raw = 'Here is the JSON you asked for: {"a": 1} — hope that helps!'
        assert json.loads(clean_model_json(raw)) == {"a": 1}

    def test_does_not_narrow_to_an_array_by_default(self):
        # Callers of clean_model_json expect an object and call .get() OUTSIDE
        # the try that wraps json.loads. Handing them a valid array turns a
        # caught JSONDecodeError into an uncaught AttributeError.
        with pytest.raises(json.JSONDecodeError):
            json.loads(clean_model_json("Results: [1, 2, 3]"))

    def test_narrows_to_array_when_explicitly_allowed(self):
        assert json.loads(clean_model_json("Results: [1, 2, 3]", allow_array=True)) == [1, 2, 3]

    def test_prefers_object_over_array(self):
        # Matches what every local copy did — the payload is an object whose
        # values may contain arrays, not the other way round.
        assert json.loads(clean_model_json('{"xs": [1, 2]}')) == {"xs": [1, 2]}

    def test_rewrites_python_literals(self):
        # Gemini emits these regularly. ticket_draft_service's local copy lacked
        # this fixup and therefore failed to parse such responses outright.
        raw = '{"ok": True, "bad": False, "note": None}'
        assert json.loads(clean_model_json(raw)) == {
            "ok": True,
            "bad": False,
            "note": None,
        }

    def test_does_not_rewrite_literals_inside_strings(self):
        raw = '{"note": "None of the True positives were False alarms"}'
        assert (
            json.loads(clean_model_json(raw))["note"]
            == "None of the True positives were False alarms"
        )

    def test_does_not_rewrite_literals_after_a_colon_inside_a_string(self):
        # The regression the scanner exists for. The old implementation anchored
        # on a colon and claimed that confined it to value positions — but string
        # values contain colons, so "Status: True positive" became
        # "Status: true positive". The first version of the test above used a
        # string with no internal colon and so passed against the broken code.
        raw = '{"note": "Status: True positive confirmed", "ok": True}'
        parsed = json.loads(clean_model_json(raw))
        assert parsed["note"] == "Status: True positive confirmed"
        assert parsed["ok"] is True

    def test_rewrites_literals_in_nested_and_array_positions(self):
        raw = '{"a": {"b": None}, "xs": [True, False, None]}'
        assert json.loads(clean_model_json(raw)) == {
            "a": {"b": None},
            "xs": [True, False, None],
        }

    def test_respects_escaped_quotes_when_tracking_string_state(self):
        # An escaped quote inside a string must not read as the string's end, or
        # every literal after it would be treated as outside-a-string.
        raw = '{"q": "he said \\"Status: None\\" loudly", "v": None}'
        parsed = json.loads(clean_model_json(raw))
        assert parsed["q"] == 'he said "Status: None" loudly'
        assert parsed["v"] is None

    def test_leaves_quoted_literals_used_as_keys_alone(self):
        raw = '{"True": 1, "None": 2}'
        assert json.loads(clean_model_json(raw)) == {"True": 1, "None": 2}


class TestParseModelJson:
    def test_parses_clean_json(self):
        assert parse_model_json('{"a": 1}') == {"a": 1}

    def test_parses_fenced_json(self):
        assert parse_model_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_parses_json_buried_in_prose_with_python_literals(self):
        raw = 'Sure!\n```json\n{"ok": True, "items": [1, 2]}\n```\nLet me know.'
        assert parse_model_json(raw) == {"ok": True, "items": [1, 2]}

    def test_returns_default_instead_of_raising(self):
        # The contract difference that kept protocol_analysis_service and
        # accommodation_service OFF this helper: they let json.loads raise so the
        # caller can react. Swapping them in would turn that into a silent default.
        assert parse_model_json("not json at all") is None
        assert parse_model_json("not json at all", default={}) == {}

    def test_empty_input_returns_default(self):
        assert parse_model_json("", default=[]) == []
        assert parse_model_json(None, default=[]) == []

    @pytest.mark.parametrize(
        "raw",
        [
            '{"a": 1}',
            '```json\n{"a": 1}\n```',
            '```\n{"a": 1}```',
            'prose {"a": 1} prose',
            '```json\n{"a": 1}',
        ],
    )
    def test_shapes_the_model_actually_emits(self, raw):
        assert parse_model_json(raw) == {"a": 1}
