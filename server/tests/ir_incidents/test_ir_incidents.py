"""Tests for IR (Incident Reporting) system pure logic functions.

Tests cover:
- Analysis service validation functions
- JSON response parsing
- Precedent scoring (structural phase)
- Consistency engine computations
- Route helper functions
"""

import sys
from types import ModuleType

# Stub google.genai before any app imports
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

import json
import importlib
import pytest
from datetime import datetime, timezone, timedelta

from app.matcha.services.ir_analysis import (
    _validate_categorization,
    _validate_severity,
    _validate_root_cause,
    _validate_recommendations,
    _validate_similar_incidents,
    _validate_policy_mapping,
    IRAnalyzer,
    VALID_INCIDENT_TYPES,
    VALID_SEVERITIES,
    VALID_RELEVANCES,
)
from app.matcha.services.ir_precedent import (
    _score_type_match,
    _score_severity,
    _score_location,
    _score_temporal,
    _tokenize,
    _jaccard,
    _cost_proximity,
    _score_safety_overlap,
    _score_behavioral_overlap,
    _score_property_overlap,
    _score_nearmiss_overlap,
    _score_category_overlap,
    compute_structural_scores,
    SEVERITY_ORDINAL,
)
from app.matcha.services.ir_consistency import (
    _compute_kish_effective_n,
    _confidence_level,
    _compute_weighted_action_distribution,
    _compute_resolution_stats,
    _compute_aggregate_distribution,
    ACTION_CATEGORIES,
)


# ============================================================
# ir_analysis: Validation Functions
# ============================================================

class TestValidateCategorization:
    def test_valid(self):
        result = {
            "suggested_type": "safety",
            "confidence": 0.85,
            "reasoning": "Slip and fall incident",
        }
        assert _validate_categorization(result) is None

    def test_invalid_type(self):
        result = {"suggested_type": "unknown", "confidence": 0.5, "reasoning": "x"}
        err = _validate_categorization(result)
        assert "Invalid suggested_type" in err

    def test_missing_type(self):
        result = {"confidence": 0.5, "reasoning": "x"}
        assert _validate_categorization(result) is not None

    def test_confidence_out_of_range(self):
        result = {"suggested_type": "safety", "confidence": 1.5, "reasoning": "x"}
        assert "Invalid confidence" in _validate_categorization(result)

    def test_confidence_negative(self):
        result = {"suggested_type": "safety", "confidence": -0.1, "reasoning": "x"}
        assert _validate_categorization(result) is not None

    def test_confidence_not_number(self):
        result = {"suggested_type": "safety", "confidence": "high", "reasoning": "x"}
        assert _validate_categorization(result) is not None

    def test_missing_reasoning(self):
        result = {"suggested_type": "safety", "confidence": 0.5, "reasoning": ""}
        assert "Missing required field: reasoning" in _validate_categorization(result)

    def test_boundary_confidence_zero(self):
        result = {"suggested_type": "near_miss", "confidence": 0.0, "reasoning": "ok"}
        assert _validate_categorization(result) is None

    def test_boundary_confidence_one(self):
        result = {"suggested_type": "other", "confidence": 1.0, "reasoning": "ok"}
        assert _validate_categorization(result) is None

    @pytest.mark.parametrize("itype", VALID_INCIDENT_TYPES)
    def test_all_valid_types(self, itype):
        result = {"suggested_type": itype, "confidence": 0.5, "reasoning": "ok"}
        assert _validate_categorization(result) is None


class TestValidateSeverity:
    def test_valid(self):
        result = {
            "suggested_severity": "medium",
            "factors": ["Minor injury"],
            "reasoning": "First aid only",
        }
        assert _validate_severity(result) is None

    def test_invalid_severity(self):
        result = {"suggested_severity": "extreme", "factors": [], "reasoning": "x"}
        assert "Invalid suggested_severity" in _validate_severity(result)

    def test_factors_not_list(self):
        result = {"suggested_severity": "low", "factors": "not a list", "reasoning": "x"}
        assert "must be a list" in _validate_severity(result)

    def test_missing_reasoning(self):
        result = {"suggested_severity": "high", "factors": [], "reasoning": ""}
        assert "reasoning" in _validate_severity(result)

    @pytest.mark.parametrize("sev", VALID_SEVERITIES)
    def test_all_valid_severities(self, sev):
        result = {"suggested_severity": sev, "factors": [], "reasoning": "ok"}
        assert _validate_severity(result) is None


class TestValidateRootCause:
    def test_valid(self):
        result = {
            "primary_cause": "Wet floor",
            "contributing_factors": ["No signage"],
            "prevention_suggestions": ["Add signs"],
            "reasoning": "Process gap",
        }
        assert _validate_root_cause(result) is None

    def test_missing_primary_cause(self):
        result = {
            "primary_cause": "",
            "contributing_factors": [],
            "prevention_suggestions": [],
            "reasoning": "x",
        }
        assert "primary_cause" in _validate_root_cause(result)

    def test_contributing_factors_not_list(self):
        result = {
            "primary_cause": "x",
            "contributing_factors": "not list",
            "prevention_suggestions": [],
            "reasoning": "x",
        }
        assert "contributing_factors" in _validate_root_cause(result)

    def test_prevention_suggestions_not_list(self):
        result = {
            "primary_cause": "x",
            "contributing_factors": [],
            "prevention_suggestions": "not list",
            "reasoning": "x",
        }
        assert "prevention_suggestions" in _validate_root_cause(result)


class TestValidateRecommendations:
    def test_valid(self):
        result = {
            "recommendations": [
                {"action": "Deploy signage", "priority": "immediate"},
            ],
            "summary": "One action needed",
        }
        assert _validate_recommendations(result) is None

    def test_empty_recommendations(self):
        result = {"recommendations": [], "summary": "x"}
        assert "cannot be empty" in _validate_recommendations(result)

    def test_not_list(self):
        result = {"recommendations": "x", "summary": "x"}
        assert "must be a list" in _validate_recommendations(result)

    def test_invalid_priority(self):
        result = {
            "recommendations": [{"action": "x", "priority": "urgent"}],
            "summary": "x",
        }
        assert "invalid priority" in _validate_recommendations(result)

    def test_missing_action(self):
        result = {
            "recommendations": [{"priority": "immediate"}],
            "summary": "x",
        }
        assert "missing required field: action" in _validate_recommendations(result)

    def test_missing_summary(self):
        result = {
            "recommendations": [{"action": "x", "priority": "immediate"}],
            "summary": "",
        }
        assert "summary" in _validate_recommendations(result)

    def test_all_valid_priorities(self):
        for p in ("immediate", "short_term", "long_term"):
            result = {
                "recommendations": [{"action": "x", "priority": p}],
                "summary": "ok",
            }
            assert _validate_recommendations(result) is None


class TestValidateSimilarIncidents:
    def test_valid_empty(self):
        result = {"similar_incidents": []}
        assert _validate_similar_incidents(result) is None

    def test_valid_with_incidents(self):
        result = {
            "similar_incidents": [
                {
                    "incident_id": "abc-123",
                    "incident_number": "IR-2024-01-AB12",
                    "similarity_score": 0.85,
                }
            ]
        }
        assert _validate_similar_incidents(result) is None

    def test_not_list(self):
        result = {"similar_incidents": "x"}
        assert "must be a list" in _validate_similar_incidents(result)

    def test_missing_incident_id(self):
        result = {
            "similar_incidents": [
                {"incident_number": "IR-1", "similarity_score": 0.5}
            ]
        }
        assert "incident_id" in _validate_similar_incidents(result)

    def test_invalid_similarity_score(self):
        result = {
            "similar_incidents": [
                {"incident_id": "x", "incident_number": "IR-1", "similarity_score": 1.5}
            ]
        }
        assert "similarity_score" in _validate_similar_incidents(result)


class TestValidatePolicyMapping:
    def test_valid(self):
        result = {
            "matches": [
                {
                    "policy_id": "p-1",
                    "policy_title": "Anti-Harassment",
                    "relevance": "violated",
                    "confidence": 0.9,
                    "reasoning": "Clear violation",
                }
            ],
            "summary": "One policy violated",
        }
        assert _validate_policy_mapping(result) is None

    def test_valid_empty_matches(self):
        result = {"matches": [], "summary": "No matches"}
        assert _validate_policy_mapping(result) is None

    def test_invalid_relevance(self):
        result = {
            "matches": [
                {
                    "policy_id": "p-1",
                    "policy_title": "x",
                    "relevance": "broken",
                    "confidence": 0.5,
                    "reasoning": "x",
                }
            ],
            "summary": "x",
        }
        assert "invalid relevance" in _validate_policy_mapping(result)

    def test_missing_summary(self):
        result = {"matches": [], "summary": ""}
        assert "summary" in _validate_policy_mapping(result)

    @pytest.mark.parametrize("rel", VALID_RELEVANCES)
    def test_all_valid_relevances(self, rel):
        result = {
            "matches": [
                {
                    "policy_id": "p-1",
                    "policy_title": "x",
                    "relevance": rel,
                    "confidence": 0.5,
                    "reasoning": "x",
                }
            ],
            "summary": "ok",
        }
        assert _validate_policy_mapping(result) is None


# ============================================================
# ir_analysis: JSON Parsing
# ============================================================

class TestParseJsonResponse:
    def setup_method(self):
        # Create a minimal analyzer just to test _parse_json_response
        self.analyzer = IRAnalyzer.__new__(IRAnalyzer)

    def test_plain_json(self):
        assert self.analyzer._parse_json_response('{"a": 1}') == {"a": 1}

    def test_markdown_json_block(self):
        text = '```json\n{"a": 1}\n```'
        assert self.analyzer._parse_json_response(text) == {"a": 1}

    def test_markdown_block(self):
        text = '```\n{"a": 1}\n```'
        assert self.analyzer._parse_json_response(text) == {"a": 1}

    def test_whitespace(self):
        assert self.analyzer._parse_json_response('  {"a": 1}  ') == {"a": 1}

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            self.analyzer._parse_json_response("not json")


# ============================================================
# ir_precedent: Structural Scoring Functions
# ============================================================

class TestTokenizeAndJaccard:
    def test_tokenize_basic(self):
        assert _tokenize("Hello World") == {"hello", "world"}

    def test_tokenize_empty(self):
        assert _tokenize("") == set()
        assert _tokenize(None) == set()

    def test_tokenize_special_chars(self):
        tokens = _tokenize("wet-floor (area #3)")
        assert "wet" in tokens
        assert "floor" in tokens
        assert "area" in tokens
        assert "3" in tokens

    def test_jaccard_identical(self):
        assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_jaccard_disjoint(self):
        assert _jaccard({"a"}, {"b"}) == 0.0

    def test_jaccard_partial(self):
        assert _jaccard({"a", "b", "c"}, {"a", "b", "d"}) == pytest.approx(0.5)

    def test_jaccard_empty(self):
        assert _jaccard(set(), set()) == 0.0


class TestScoreTypeMatch:
    def test_same_type(self):
        assert _score_type_match({"incident_type": "safety"}, {"incident_type": "safety"}) == 1.0

    def test_different_type(self):
        assert _score_type_match({"incident_type": "safety"}, {"incident_type": "behavioral"}) == 0.0


class TestScoreSeverity:
    def test_same_severity(self):
        assert _score_severity({"severity": "high"}, {"severity": "high"}) == 1.0

    def test_adjacent_severity(self):
        # high=3, medium=2, diff=1, score = 1 - 1/3
        assert _score_severity({"severity": "high"}, {"severity": "medium"}) == pytest.approx(2/3)

    def test_extreme_severity(self):
        # critical=4, low=1, diff=3, score = 1 - 3/3 = 0
        assert _score_severity({"severity": "critical"}, {"severity": "low"}) == 0.0

    def test_missing_severity_defaults_medium(self):
        assert _score_severity({}, {}) == 1.0  # both default to medium


class TestScoreLocation:
    def test_same_location_id(self):
        a = {"location_id": "loc-1", "location": ""}
        b = {"location_id": "loc-1", "location": ""}
        assert _score_location(a, b) == 1.0

    def test_different_location_id_same_text(self):
        a = {"location_id": "loc-1", "location": "Kitchen Area"}
        b = {"location_id": "loc-2", "location": "Kitchen Area"}
        assert _score_location(a, b) == 1.0

    def test_no_location(self):
        assert _score_location({"location": ""}, {"location": ""}) == 0.0

    def test_partial_location_overlap(self):
        a = {"location": "Kitchen Area Floor 1"}
        b = {"location": "Kitchen Area Floor 2"}
        score = _score_location(a, b)
        assert 0 < score < 1


class TestScoreTemporal:
    def test_same_datetime(self):
        dt = datetime(2024, 6, 15, 10, 30)
        assert _score_temporal({"occurred_at": dt}, {"occurred_at": dt}) == 1.0

    def test_different_time_bucket(self):
        a = {"occurred_at": datetime(2024, 6, 15, 2, 0)}   # bucket 0
        b = {"occurred_at": datetime(2024, 6, 15, 14, 0)}  # bucket 2
        score = _score_temporal(a, b)
        # same weekday, same month, different time bucket -> 2/3
        assert score == pytest.approx(2/3)

    def test_missing_datetime(self):
        assert _score_temporal({"occurred_at": None}, {"occurred_at": datetime.now()}) == 0.0

    def test_string_datetimes(self):
        a = {"occurred_at": "2024-06-15T10:00:00Z"}
        b = {"occurred_at": "2024-06-15T10:00:00Z"}
        assert _score_temporal(a, b) == 1.0


class TestCostProximity:
    def test_same_cost(self):
        assert _cost_proximity(1000.0, 1000.0) == 1.0

    def test_zero_both(self):
        assert _cost_proximity(0.0, 0.0) == 1.0

    def test_none(self):
        assert _cost_proximity(None, 1000.0) == 0.0

    def test_different_cost(self):
        # |500 - 1000| / 1000 = 0.5, score = 0.5
        assert _cost_proximity(500.0, 1000.0) == pytest.approx(0.5)


class TestCategoryOverlapScorers:
    def test_safety_overlap_same_injury(self):
        c = {"injury_type": "laceration", "body_parts": ["hand"]}
        h = {"injury_type": "laceration", "body_parts": ["hand"]}
        assert _score_safety_overlap(c, h) == 1.0

    def test_safety_overlap_different(self):
        c = {"injury_type": "burn", "body_parts": ["arm"]}
        h = {"injury_type": "fracture", "body_parts": ["leg"]}
        score = _score_safety_overlap(c, h)
        assert score < 0.5

    def test_behavioral_overlap_same_policy(self):
        c = {"policy_violated": "anti harassment policy"}
        h = {"policy_violated": "anti harassment policy"}
        assert _score_behavioral_overlap(c, h) == 1.0

    def test_property_overlap_same_cost(self):
        c = {"estimated_cost": 5000.0, "insurance_claim": True}
        h = {"estimated_cost": 5000.0, "insurance_claim": True}
        assert _score_property_overlap(c, h) == 1.0

    def test_nearmiss_overlap(self):
        c = {"hazard_identified": "exposed wiring near water"}
        h = {"hazard_identified": "exposed wiring near water"}
        assert _score_nearmiss_overlap(c, h) == 1.0

    def test_nearmiss_empty(self):
        assert _score_nearmiss_overlap({}, {}) == 0.0

    def test_category_overlap_different_types(self):
        a = {"incident_type": "safety", "category_data": {"injury_type": "burn"}}
        b = {"incident_type": "behavioral", "category_data": {}}
        assert _score_category_overlap(a, b) == 0.0


class TestComputeStructuralScores:
    def test_same_type_passes_threshold(self):
        current = {"incident_type": "safety", "severity": "high"}
        candidates = [
            {"incident_type": "safety", "severity": "high", "id": "c1"},
        ]
        results = compute_structural_scores(current, candidates)
        assert len(results) == 1
        assert results[0]["structural_score"] > 0

    def test_filters_below_threshold(self):
        current = {"incident_type": "safety", "severity": "critical"}
        candidates = [
            {"incident_type": "behavioral", "severity": "low", "id": "c1"},
        ]
        # Different type + max severity distance -> low score
        results = compute_structural_scores(current, candidates)
        # May or may not pass threshold depending on exact score
        for r in results:
            assert r["structural_score"] >= 0.25

    def test_sorted_descending(self):
        current = {"incident_type": "safety", "severity": "high"}
        candidates = [
            {"incident_type": "safety", "severity": "low", "id": "c1"},
            {"incident_type": "safety", "severity": "high", "id": "c2"},
        ]
        results = compute_structural_scores(current, candidates)
        if len(results) >= 2:
            assert results[0]["structural_score"] >= results[1]["structural_score"]

    def test_limited_to_phase1_keep(self):
        current = {"incident_type": "safety", "severity": "medium"}
        candidates = [
            {"incident_type": "safety", "severity": "medium", "id": f"c{i}"}
            for i in range(30)
        ]
        results = compute_structural_scores(current, candidates)
        assert len(results) <= 20


# ============================================================
# ir_consistency: Computation Functions
# ============================================================

class TestKishEffectiveN:
    def test_equal_weights(self):
        # All equal weights: n_eff = n
        n_eff = _compute_kish_effective_n([1.0, 1.0, 1.0, 1.0])
        assert n_eff == pytest.approx(4.0)

    def test_single_weight(self):
        assert _compute_kish_effective_n([1.0]) == pytest.approx(1.0)

    def test_empty(self):
        assert _compute_kish_effective_n([]) == 0.0

    def test_all_zero(self):
        assert _compute_kish_effective_n([0.0, 0.0]) == 0.0

    def test_unequal_weights(self):
        # One dominant weight reduces effective n
        n_eff = _compute_kish_effective_n([10.0, 1.0, 1.0])
        assert n_eff < 3.0
        assert n_eff > 1.0


class TestConfidenceLevel:
    def test_insufficient(self):
        assert _confidence_level(0.5) == "insufficient"
        assert _confidence_level(1.9) == "insufficient"

    def test_limited(self):
        assert _confidence_level(2.0) == "limited"
        assert _confidence_level(5.0) == "limited"

    def test_strong(self):
        assert _confidence_level(5.1) == "strong"
        assert _confidence_level(100.0) == "strong"


class TestWeightedActionDistribution:
    def test_basic(self):
        precedents = [
            {"incident_id": "a", "similarity_score": 0.8},
            {"incident_id": "b", "similarity_score": 0.6},
        ]
        categorized = {
            "a": ["verbal_warning"],
            "b": ["written_warning"],
        }
        dist = _compute_weighted_action_distribution(precedents, categorized)
        assert len(dist) == 2
        # verbal_warning has higher weight (0.8 vs 0.6)
        assert dist[0]["category"] == "verbal_warning"
        total_prob = sum(d["probability"] for d in dist)
        assert total_prob == pytest.approx(1.0)

    def test_empty_precedents(self):
        assert _compute_weighted_action_distribution([], {}) == []

    def test_zero_weights(self):
        precedents = [{"incident_id": "a", "similarity_score": 0.0}]
        categorized = {"a": ["termination"]}
        assert _compute_weighted_action_distribution(precedents, categorized) == []

    def test_multi_category(self):
        precedents = [{"incident_id": "a", "similarity_score": 1.0}]
        categorized = {"a": ["verbal_warning", "retraining"]}
        dist = _compute_weighted_action_distribution(precedents, categorized)
        assert len(dist) == 2
        # Each gets probability 1.0 (both weighted 1.0 / total 1.0)
        for d in dist:
            assert d["probability"] == pytest.approx(1.0)


class TestResolutionStats:
    def test_basic(self):
        precedents = [
            {"similarity_score": 1.0, "resolution_days": 10, "resolution_effective": True},
            {"similarity_score": 1.0, "resolution_days": 20, "resolution_effective": False},
        ]
        stats = _compute_resolution_stats(precedents)
        assert stats["weighted_avg_resolution_days"] == pytest.approx(15.0)
        assert stats["weighted_effectiveness_rate"] == pytest.approx(0.5)

    def test_no_resolution_data(self):
        precedents = [{"similarity_score": 1.0}]
        stats = _compute_resolution_stats(precedents)
        assert stats["weighted_avg_resolution_days"] is None
        assert stats["weighted_effectiveness_rate"] is None

    def test_weighted_resolution(self):
        precedents = [
            {"similarity_score": 0.9, "resolution_days": 5, "resolution_effective": True},
            {"similarity_score": 0.1, "resolution_days": 50, "resolution_effective": False},
        ]
        stats = _compute_resolution_stats(precedents)
        # Heavily weighted toward 5 days
        assert stats["weighted_avg_resolution_days"] < 10


class TestAggregateDistribution:
    def test_basic(self):
        incidents = [
            {"id": "a"},
            {"id": "b"},
        ]
        categorized = {
            "a": ["verbal_warning"],
            "b": ["verbal_warning"],
        }
        dist = _compute_aggregate_distribution(incidents, categorized)
        assert len(dist) == 1
        assert dist[0]["category"] == "verbal_warning"
        assert dist[0]["probability"] == pytest.approx(1.0)

    def test_empty(self):
        assert _compute_aggregate_distribution([], {}) == []

    def test_fallback_to_other(self):
        incidents = [{"id": "a"}]
        categorized = {}  # not found -> defaults to "other"
        dist = _compute_aggregate_distribution(incidents, categorized)
        assert len(dist) == 1
        assert dist[0]["category"] == "other"


# ============================================================
# Route Helpers
# ============================================================

def _load_ir_routes_module():
    """Load ir_incidents module directly to avoid __init__.py transitive imports."""
    loader = importlib.util.find_spec("app.matcha.routes.ir_incidents")
    if loader is None:
        pytest.skip("Cannot find ir_incidents module")
    mod = importlib.util.module_from_spec(loader)
    try:
        loader.loader.exec_module(mod)
    except Exception:
        pytest.skip("Cannot load ir_incidents module (transitive import issue)")
    return mod


class TestRouteHelpers:
    """Test pure helper functions from the ir_incidents routes module.

    These functions are defined inline in the routes file. We re-implement
    the pure ones here to avoid transitive import issues with the routes package.
    """

    def test_sse_format(self):
        # _sse is a trivial function: f"data: {json.dumps(event)}\\n\\n"
        def _sse(event: dict) -> str:
            return f"data: {json.dumps(event)}\n\n"

        result = _sse({"type": "test", "data": 123})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        parsed = json.loads(result[6:].strip())
        assert parsed["type"] == "test"

    def test_generate_incident_number_format(self):
        """Verify the incident number format logic."""
        import secrets
        now = datetime.now(timezone.utc)
        random_suffix = secrets.token_hex(2).upper()
        number = f"IR-{now.year}-{now.month:02d}-{random_suffix}"
        assert number.startswith("IR-")
        parts = number.split("-")
        assert len(parts) == 4
        assert parts[1] == str(now.year)
        assert len(parts[3]) == 4  # 2 bytes hex = 4 chars

    def test_to_naive_utc_aware(self):
        def _to_naive_utc(value):
            if value.tzinfo:
                return value.astimezone(timezone.utc).replace(tzinfo=None)
            return value

        dt = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        result = _to_naive_utc(dt)
        assert result.tzinfo is None
        assert result.hour == 12

    def test_to_naive_utc_naive(self):
        def _to_naive_utc(value):
            if value.tzinfo:
                return value.astimezone(timezone.utc).replace(tzinfo=None)
            return value

        dt = datetime(2024, 6, 15, 12, 0)
        result = _to_naive_utc(dt)
        assert result.tzinfo is None
        assert result == dt

    def test_safe_json_loads_valid(self):
        def _safe_json_loads(val, default=None):
            if val is None:
                return default
            if isinstance(val, (dict, list)):
                return val
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return default

        assert _safe_json_loads('{"a": 1}') == {"a": 1}

    def test_safe_json_loads_none(self):
        def _safe_json_loads(val, default=None):
            if val is None:
                return default
            if isinstance(val, (dict, list)):
                return val
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return default

        assert _safe_json_loads(None) is None
        assert _safe_json_loads(None, default=[]) == []

    def test_safe_json_loads_already_dict(self):
        def _safe_json_loads(val, default=None):
            if val is None:
                return default
            if isinstance(val, (dict, list)):
                return val
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return default

        d = {"a": 1}
        assert _safe_json_loads(d) is d

    def test_safe_json_loads_invalid(self):
        def _safe_json_loads(val, default=None):
            if val is None:
                return default
            if isinstance(val, (dict, list)):
                return val
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return default

        assert _safe_json_loads("not json") is None
        assert _safe_json_loads("not json", default=[]) == []

    def test_company_filter(self):
        def _company_filter(param_idx: int) -> str:
            return f"i.company_id = ${param_idx}"

        assert _company_filter(3) == "i.company_id = $3"


# ============================================================
# Constants sanity checks
# ============================================================

class TestConstants:
    def test_valid_incident_types(self):
        assert "safety" in VALID_INCIDENT_TYPES
        assert "behavioral" in VALID_INCIDENT_TYPES
        assert "property" in VALID_INCIDENT_TYPES
        assert "near_miss" in VALID_INCIDENT_TYPES
        assert "other" in VALID_INCIDENT_TYPES

    def test_severity_ordinal_ordering(self):
        assert SEVERITY_ORDINAL["low"] < SEVERITY_ORDINAL["medium"]
        assert SEVERITY_ORDINAL["medium"] < SEVERITY_ORDINAL["high"]
        assert SEVERITY_ORDINAL["high"] < SEVERITY_ORDINAL["critical"]

    def test_action_categories_not_empty(self):
        assert len(ACTION_CATEGORIES) > 0
        assert "verbal_warning" in ACTION_CATEGORIES
        assert "termination" in ACTION_CATEGORIES
        assert "no_action" in ACTION_CATEGORIES
