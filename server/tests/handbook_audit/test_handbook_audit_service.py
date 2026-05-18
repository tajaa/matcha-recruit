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

from datetime import date

from app.core.services.handbook_audit_service import (
    MAX_REQUIREMENTS_PER_STATE,
    MAX_SECTIONS_FOR_PROMPT,
    SAMPLE_GAPS_COUNT,
    _collapse_same_level_jurisdictions,
    _merge_duplicate_gaps_for_state,
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


# ============================================================
# _collapse_same_level_jurisdictions — pre-Gemini topic dedup
# ============================================================

class TestCollapseSameLevelJurisdictions:
    def test_empty_list(self):
        assert _collapse_same_level_jurisdictions([]) == []

    def test_single_row_unchanged(self):
        req = {
            "category": "sick_leave", "rate_type": None,
            "jurisdiction_level": "state", "jurisdiction_name": "CA",
            "title": "Paid Sick Leave", "description": "...", "source_url": "u",
            "effective_date": date(2024, 1, 1),
        }
        result = _collapse_same_level_jurisdictions([req])
        assert len(result) == 1
        # Original fields preserved.
        assert result[0]["category"] == "sick_leave"
        assert result[0]["jurisdiction_name"] == "CA"
        # also_jurisdictions present + empty.
        assert result[0]["also_jurisdictions"] == []

    def test_three_cities_same_category_collapse(self):
        reqs = [
            {"category": "sick_leave", "rate_type": None,
             "jurisdiction_level": "city", "jurisdiction_name": "Los Angeles",
             "title": "LA Sick Leave", "description": "short",
             "effective_date": date(2024, 1, 1), "source_url": "la"},
            {"category": "sick_leave", "rate_type": None,
             "jurisdiction_level": "city", "jurisdiction_name": "San Francisco",
             "title": "SF Sick Leave", "description": "shorter",
             "effective_date": date(2023, 6, 1), "source_url": "sf"},
            {"category": "sick_leave", "rate_type": None,
             "jurisdiction_level": "city", "jurisdiction_name": "Berkeley",
             "title": "BRK Sick Leave", "description": "short",
             "effective_date": date(2023, 1, 1), "source_url": "brk"},
        ]
        result = _collapse_same_level_jurisdictions(reqs)
        assert len(result) == 1
        rep = result[0]
        # Newest effective_date wins → Los Angeles.
        assert rep["jurisdiction_name"] == "Los Angeles"
        assert len(rep["also_jurisdictions"]) == 2
        names = {j["name"] for j in rep["also_jurisdictions"]}
        assert names == {"San Francisco", "Berkeley"}
        # Sibling shape.
        assert all("level" in j and "source_url" in j for j in rep["also_jurisdictions"])

    def test_different_rate_types_kept_separate(self):
        reqs = [
            {"category": "final_pay", "rate_type": "voluntary",
             "jurisdiction_level": "state", "jurisdiction_name": "CA",
             "title": "Voluntary", "effective_date": date(2024, 1, 1)},
            {"category": "final_pay", "rate_type": "involuntary",
             "jurisdiction_level": "state", "jurisdiction_name": "CA",
             "title": "Involuntary", "effective_date": date(2024, 1, 1)},
        ]
        result = _collapse_same_level_jurisdictions(reqs)
        assert len(result) == 2
        rate_types = {r["rate_type"] for r in result}
        assert rate_types == {"voluntary", "involuntary"}

    def test_picks_most_recent_effective_date(self):
        reqs = [
            {"category": "wage", "rate_type": "minimum", "jurisdiction_level": "city",
             "jurisdiction_name": "A", "title": "older",
             "effective_date": date(2020, 1, 1), "description": "short"},
            {"category": "wage", "rate_type": "minimum", "jurisdiction_level": "city",
             "jurisdiction_name": "B", "title": "newest",
             "effective_date": date(2025, 1, 1), "description": "short"},
            {"category": "wage", "rate_type": "minimum", "jurisdiction_level": "city",
             "jurisdiction_name": "C", "title": "middle",
             "effective_date": date(2022, 1, 1), "description": "short"},
        ]
        result = _collapse_same_level_jurisdictions(reqs)
        assert result[0]["jurisdiction_name"] == "B"
        assert result[0]["title"] == "newest"

    def test_tie_break_longest_description(self):
        reqs = [
            {"category": "wage", "rate_type": None, "jurisdiction_level": "state",
             "jurisdiction_name": "A", "effective_date": date(2024, 1, 1),
             "description": "short"},
            {"category": "wage", "rate_type": None, "jurisdiction_level": "state",
             "jurisdiction_name": "B", "effective_date": date(2024, 1, 1),
             "description": "this description is significantly longer"},
        ]
        result = _collapse_same_level_jurisdictions(reqs)
        assert result[0]["jurisdiction_name"] == "B"

    def test_rows_without_category_pass_through(self):
        reqs = [
            {"category": "", "title": "No category", "jurisdiction_level": "state",
             "jurisdiction_name": "X"},
            {"category": None, "title": "Also nothing", "jurisdiction_level": "state",
             "jurisdiction_name": "Y"},
            {"category": "sick_leave", "rate_type": None,
             "jurisdiction_level": "state", "jurisdiction_name": "CA",
             "title": "Sick Leave", "effective_date": date(2024, 1, 1)},
        ]
        result = _collapse_same_level_jurisdictions(reqs)
        # 1 grouped + 2 ungrouped passthrough.
        assert len(result) == 3
        titles = [r["title"] for r in result]
        assert "Sick Leave" in titles
        assert "No category" in titles
        assert "Also nothing" in titles

    def test_does_not_mutate_input(self):
        original = [
            {"category": "sick_leave", "rate_type": None, "jurisdiction_level": "city",
             "jurisdiction_name": "A", "effective_date": date(2024, 1, 1)},
            {"category": "sick_leave", "rate_type": None, "jurisdiction_level": "city",
             "jurisdiction_name": "B", "effective_date": date(2023, 1, 1)},
        ]
        snapshot = [dict(r) for r in original]
        _collapse_same_level_jurisdictions(original)
        for before, after in zip(snapshot, original):
            assert before == after


# ============================================================
# _merge_duplicate_gaps_for_state — post-Gemini safety net
# ============================================================

class TestMergeDuplicateGapsForState:
    def _empty_counts(self):
        return {"critical": 0, "important": 0, "recommended": 0, "covered": 0}

    def test_no_duplicates(self):
        gaps = [
            {"requirement_key": "a", "requirement_title": "A", "covered": False,
             "severity": "critical"},
            {"requirement_key": "b", "requirement_title": "B", "covered": False,
             "severity": "important"},
            {"requirement_key": "c", "requirement_title": "C", "covered": False,
             "severity": "recommended"},
        ]
        per = self._empty_counts()
        result = _merge_duplicate_gaps_for_state("CA", gaps, per)
        assert len(result) == 3
        assert per == {"critical": 1, "important": 1, "recommended": 1, "covered": 0}
        for g in result:
            assert g["state"] == "CA"
            assert g["also_covers"] == []

    def test_two_same_key_severity_promoted(self):
        gaps = [
            {"requirement_key": "wage", "requirement_title": "Wage A",
             "covered": False, "severity": "important"},
            {"requirement_key": "wage", "requirement_title": "Wage B",
             "covered": False, "severity": "critical"},
        ]
        per = self._empty_counts()
        result = _merge_duplicate_gaps_for_state("CA", gaps, per)
        assert len(result) == 1
        assert result[0]["severity"] == "critical"
        assert result[0]["also_covers"] == ["Wage B"]
        assert per["critical"] == 1
        assert per["important"] == 0

    def test_three_same_key_promotion(self):
        gaps = [
            {"requirement_key": "x", "requirement_title": "X1", "covered": False,
             "severity": "recommended"},
            {"requirement_key": "x", "requirement_title": "X2", "covered": False,
             "severity": "important"},
            {"requirement_key": "x", "requirement_title": "X3", "covered": False,
             "severity": "critical"},
        ]
        per = self._empty_counts()
        result = _merge_duplicate_gaps_for_state("CA", gaps, per)
        assert len(result) == 1
        assert result[0]["severity"] == "critical"
        assert sorted(result[0]["also_covers"]) == ["X2", "X3"]
        assert per["recommended"] == 0
        assert per["important"] == 0
        assert per["critical"] == 1

    def test_covered_gaps_excluded(self):
        gaps = [
            {"requirement_key": "covered_key", "requirement_title": "C",
             "covered": True, "severity": "important"},
            {"requirement_key": "uncovered_key", "requirement_title": "U",
             "covered": False, "severity": "important"},
        ]
        per = self._empty_counts()
        result = _merge_duplicate_gaps_for_state("CA", gaps, per)
        assert len(result) == 1
        assert result[0]["requirement_title"] == "U"
        assert per["covered"] == 1
        assert per["important"] == 1

    def test_also_jurisdictions_merged(self):
        gaps = [
            {"requirement_key": "k", "requirement_title": "K1", "covered": False,
             "severity": "important",
             "also_jurisdictions": [{"name": "LA", "level": "city", "source_url": None}]},
            {"requirement_key": "k", "requirement_title": "K2", "covered": False,
             "severity": "important",
             "also_jurisdictions": [{"name": "SF", "level": "city", "source_url": None}]},
        ]
        per = self._empty_counts()
        result = _merge_duplicate_gaps_for_state("CA", gaps, per)
        assert len(result) == 1
        names = [j["name"] for j in result[0]["also_jurisdictions"]]
        assert names == ["LA", "SF"]

    def test_also_jurisdictions_dedup_on_name_level(self):
        gaps = [
            {"requirement_key": "k", "requirement_title": "K1", "covered": False,
             "severity": "important",
             "also_jurisdictions": [{"name": "LA", "level": "city", "source_url": None}]},
            {"requirement_key": "k", "requirement_title": "K2", "covered": False,
             "severity": "important",
             "also_jurisdictions": [{"name": "LA", "level": "city", "source_url": None}]},
        ]
        per = self._empty_counts()
        result = _merge_duplicate_gaps_for_state("CA", gaps, per)
        assert len(result[0]["also_jurisdictions"]) == 1

    def test_also_covers_dedups_on_title(self):
        gaps = [
            {"requirement_key": "k", "requirement_title": "Same Title",
             "covered": False, "severity": "important"},
            {"requirement_key": "k", "requirement_title": "Same Title",
             "covered": False, "severity": "important"},
        ]
        per = self._empty_counts()
        result = _merge_duplicate_gaps_for_state("CA", gaps, per)
        assert len(result) == 1
        # Duplicate title doesn't enter also_covers — it matches primary.
        assert result[0]["also_covers"] == []
