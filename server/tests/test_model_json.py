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

    def test_narrows_to_array_when_no_object(self):
        assert json.loads(clean_model_json("Results: [1, 2, 3]")) == [1, 2, 3]

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
        # The colon anchor is load-bearing: a bare \\bTrue\\b substitution would
        # corrupt prose that happens to contain the word.
        raw = '{"note": "None of the True positives were False alarms"}'
        assert (
            json.loads(clean_model_json(raw))["note"]
            == "None of the True positives were False alarms"
        )


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
