"""Pure-helper tests for handbook_audit_service.

End-to-end coverage (real Gemini + real S3 + real DB) lives in the
manual dev-remote smoke documented in HANDBOOK_AUDIT_SMOKE_OUTPUT.md.
This file only covers the bits that don't need network or DB.
"""

import sys
from types import ModuleType

# Stub google.genai before any app imports (matches other test files).
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

import inspect

from app.core.services.handbook_audit_service import (
    MAX_REQUIREMENTS_PER_STATE,
    MAX_SECTIONS_FOR_PROMPT,
    SAMPLE_GAPS_COUNT,
    _pick_sample_gaps,
    _strip_json_fence,
    run_handbook_audit,
)


class TestPublicSurface:
    def test_run_handbook_audit_is_async(self):
        # FastAPI BackgroundTasks supports both sync and async callables;
        # ours is async because the underlying Gemini + asyncpg work is.
        assert inspect.iscoroutinefunction(run_handbook_audit)

    def test_run_handbook_audit_takes_report_id(self):
        sig = inspect.signature(run_handbook_audit)
        params = list(sig.parameters.keys())
        assert params == ["report_id"]


class TestSampleGapPicker:
    def test_empty_input(self):
        assert _pick_sample_gaps([], 5) == []

    def test_picks_n_severity_ranked(self):
        gaps = [
            {"requirement_title": "C", "severity": "recommended", "state": "CA",
             "what_good_looks_like": "rec body"},
            {"requirement_title": "A", "severity": "critical", "state": "CA",
             "what_good_looks_like": "crit body"},
            {"requirement_title": "B", "severity": "important", "state": "CA",
             "what_good_looks_like": "imp body"},
        ]
        result = _pick_sample_gaps(gaps, 2)
        assert [g["requirement_title"] for g in result] == ["A", "B"]
        # what_good_looks_like is truncated to 280 chars — passthrough check.
        assert result[0]["what_good_looks_like"] == "crit body"

    def test_n_zero_returns_empty(self):
        gaps = [{"requirement_title": "X", "severity": "critical", "state": "CA"}]
        assert _pick_sample_gaps(gaps, 0) == []

    def test_truncates_to_280(self):
        long_body = "x" * 500
        gaps = [{"requirement_title": "A", "severity": "critical", "state": "CA",
                 "what_good_looks_like": long_body}]
        result = _pick_sample_gaps(gaps, 1)
        assert len(result[0]["what_good_looks_like"]) == 280


class TestJsonFenceStripper:
    def test_strips_json_fence(self):
        assert _strip_json_fence("```json\n{\"a\": 1}\n```") == '{"a": 1}'

    def test_strips_bare_fence(self):
        assert _strip_json_fence("```\n{\"a\": 1}\n```") == '{"a": 1}'

    def test_unfenced_passthrough(self):
        assert _strip_json_fence('{"a": 1}') == '{"a": 1}'

    def test_none_and_empty(self):
        assert _strip_json_fence("") == ""
        assert _strip_json_fence(None) == ""  # type: ignore[arg-type]

    def test_trailing_whitespace_stripped(self):
        assert _strip_json_fence("  {\"a\": 1}  ") == '{"a": 1}'


class TestModuleConstants:
    def test_constants_sane(self):
        assert MAX_REQUIREMENTS_PER_STATE > 0
        assert MAX_SECTIONS_FOR_PROMPT > 0
        assert SAMPLE_GAPS_COUNT >= 1
