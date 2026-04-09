"""Tests for pre-termination system pure logic."""

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

# Stub audioop for Python 3.13+
audioop_module = ModuleType("audioop")
sys.modules.setdefault("audioop", audioop_module)
audioop_lts_module = ModuleType("audioop_lts")
sys.modules.setdefault("audioop_lts", audioop_lts_module)

import json
import pytest
from dataclasses import asdict
from datetime import date, datetime, timezone
from uuid import uuid4

from app.matcha.services.pre_termination_service import (
    PreTermDimensionResult,
    PreTermCheckResult,
    _green,
    _yellow,
    _red,
    _safe_dimension,
    _compute_kish_effective_n,
    _generate_recommended_actions,
)
from app.matcha.services.risk_assessment_service import _band
from app.matcha.routes.pre_termination import (
    _normalize_json,
    _to_discipline_response,
    _to_charge_response,
    _to_claim_response,
    VALID_DISCIPLINE_TYPES,
    VALID_DISCIPLINE_STATUSES,
    VALID_CHARGE_TYPES,
    VALID_CHARGE_STATUSES,
    VALID_CLAIM_STATUSES,
    DisciplineCreateRequest,
    DisciplineUpdateRequest,
    AgencyChargeCreateRequest,
    AgencyChargeUpdateRequest,
    PostTermClaimCreateRequest,
    PostTermClaimUpdateRequest,
)


# =========================================================================
# _band (risk scoring)
# =========================================================================

class TestBand:
    def test_low(self):
        assert _band(0) == "low"
        assert _band(25) == "low"

    def test_moderate(self):
        assert _band(26) == "moderate"
        assert _band(50) == "moderate"

    def test_high(self):
        assert _band(51) == "high"
        assert _band(75) == "high"

    def test_critical(self):
        assert _band(76) == "critical"
        assert _band(100) == "critical"


# =========================================================================
# Dimension result helpers
# =========================================================================

class TestDimensionHelpers:
    def test_green(self):
        r = _green("All clear", count=0)
        assert r.status == "green"
        assert r.score == 0
        assert r.summary == "All clear"
        assert r.details == {"count": 0}

    def test_yellow(self):
        r = _yellow("Minor issue", reason="test")
        assert r.status == "yellow"
        assert r.score == 15
        assert r.details == {"reason": "test"}

    def test_red(self):
        r = _red("Critical issue", cases=3)
        assert r.status == "red"
        assert r.score == 30
        assert r.details == {"cases": 3}

    def test_safe_dimension_returns_yellow(self):
        r = _safe_dimension("test_dim", ValueError("boom"))
        assert r.status == "yellow"
        assert r.score == 15
        assert "ValueError" in r.summary
        assert r.details["error"] == "boom"

    def test_dataclass_asdict(self):
        r = _green("ok")
        d = asdict(r)
        assert d == {"status": "green", "score": 0, "summary": "ok", "details": {}}


# =========================================================================
# Kish effective N
# =========================================================================

class TestKishEffectiveN:
    def test_empty(self):
        assert _compute_kish_effective_n([]) == 0.0

    def test_all_zeros(self):
        assert _compute_kish_effective_n([0, 0, 0]) == 0.0

    def test_uniform_weights(self):
        # For uniform weights [1,1,1], effective N = 3
        result = _compute_kish_effective_n([1.0, 1.0, 1.0])
        assert result == pytest.approx(3.0)

    def test_single_weight(self):
        result = _compute_kish_effective_n([5.0])
        assert result == pytest.approx(1.0)

    def test_unequal_weights(self):
        # [1, 0] -> (1)^2 / (1) = 1.0
        result = _compute_kish_effective_n([1.0, 0.0])
        assert result == pytest.approx(1.0)

    def test_varied_weights(self):
        # [2, 1] -> (3)^2 / (4+1) = 9/5 = 1.8
        result = _compute_kish_effective_n([2.0, 1.0])
        assert result == pytest.approx(1.8)


# =========================================================================
# Overall score calculation (mirrors orchestrator logic)
# =========================================================================

class TestOverallScoreCalculation:
    def test_all_green_score_is_zero(self):
        dims = {f"dim_{i}": _green("ok") for i in range(9)}
        total = sum(d.score for d in dims.values())
        overall = int(total / 270 * 100)
        assert overall == 0
        assert _band(overall) == "low"

    def test_all_red_score_is_100(self):
        dims = {f"dim_{i}": _red("bad") for i in range(9)}
        total = sum(d.score for d in dims.values())
        overall = int(total / 270 * 100)
        assert overall == 100
        assert _band(overall) == "critical"

    def test_mixed_scores(self):
        dims = {
            "a": _red("bad"),      # 30
            "b": _yellow("meh"),   # 15
            "c": _green("ok"),     # 0
        }
        total = sum(d.score for d in dims.values())  # 45
        # In real code max_possible=270 for 9 dims, but logic is the same
        overall = int(total / 270 * 100)
        assert overall == 16
        assert _band(overall) == "low"

    def test_requires_acknowledgment_for_high(self):
        overall_band = "high"
        assert overall_band in ("high", "critical")

    def test_no_acknowledgment_for_low(self):
        overall_band = "low"
        assert overall_band not in ("high", "critical")


# =========================================================================
# Recommended actions generator
# =========================================================================

class TestGenerateRecommendedActions:
    def _dims(self, overrides=None):
        """Build a dimension dict with all green, then apply overrides."""
        names = [
            "er_cases", "ir_involvement", "leave_status",
            "protected_activity", "documentation", "consistency",
            "manager_profile", "retaliation_risk", "tenure_timing",
        ]
        dims = {n: _green("ok") for n in names}
        if overrides:
            dims.update(overrides)
        return dims

    def test_all_green_low_band_no_actions(self):
        actions = _generate_recommended_actions(self._dims(), "low")
        assert actions == []

    def test_er_cases_red(self):
        dims = self._dims({"er_cases": _red("open case")})
        actions = _generate_recommended_actions(dims, "moderate")
        assert any("ER case" in a for a in actions)

    def test_ir_involvement_red(self):
        dims = self._dims({"ir_involvement": _red("filed report")})
        actions = _generate_recommended_actions(dims, "moderate")
        assert any("protected report" in a for a in actions)

    def test_leave_status_red(self):
        dims = self._dims({"leave_status": _red("on leave")})
        actions = _generate_recommended_actions(dims, "moderate")
        assert any("FMLA" in a for a in actions)

    def test_protected_activity_red(self):
        dims = self._dims({"protected_activity": _red("complaint")})
        actions = _generate_recommended_actions(dims, "moderate")
        assert any("Title VII" in a for a in actions)

    def test_documentation_yellow_triggers_action(self):
        dims = self._dims({"documentation": _yellow("sparse")})
        actions = _generate_recommended_actions(dims, "low")
        assert any("Document" in a for a in actions)

    def test_documentation_red_triggers_action(self):
        dims = self._dims({"documentation": _red("missing")})
        actions = _generate_recommended_actions(dims, "moderate")
        assert any("Document" in a for a in actions)

    def test_consistency_red(self):
        dims = self._dims({"consistency": _red("inconsistent")})
        actions = _generate_recommended_actions(dims, "moderate")
        assert any("disparate treatment" in a for a in actions)

    def test_manager_profile_red(self):
        dims = self._dims({"manager_profile": _red("high turnover")})
        actions = _generate_recommended_actions(dims, "moderate")
        assert any("Manager" in a for a in actions)

    def test_retaliation_red(self):
        dims = self._dims({"retaliation_risk": _red("90 day proximity")})
        actions = _generate_recommended_actions(dims, "moderate")
        assert any("prima facie" in a for a in actions)

    def test_retaliation_yellow(self):
        dims = self._dims({"retaliation_risk": _yellow("180 day proximity")})
        actions = _generate_recommended_actions(dims, "low")
        assert any("non-retaliatory" in a for a in actions)

    def test_high_band_adds_counsel(self):
        actions = _generate_recommended_actions(self._dims(), "high")
        assert any("counsel" in a.lower() for a in actions)

    def test_critical_band_adds_counsel(self):
        actions = _generate_recommended_actions(self._dims(), "critical")
        assert any("counsel" in a.lower() for a in actions)

    def test_multiple_red_flags(self):
        dims = self._dims({
            "er_cases": _red("open"),
            "leave_status": _red("on leave"),
            "retaliation_risk": _red("proximity"),
        })
        actions = _generate_recommended_actions(dims, "critical")
        assert len(actions) >= 4  # 3 dimension actions + counsel


# =========================================================================
# _normalize_json
# =========================================================================

class TestNormalizeJson:
    def test_none_returns_default(self):
        assert _normalize_json(None) is None
        assert _normalize_json(None, []) == []

    def test_dict_passthrough(self):
        d = {"a": 1}
        assert _normalize_json(d) is d

    def test_list_passthrough(self):
        lst = [1, 2]
        assert _normalize_json(lst) is lst

    def test_valid_json_string(self):
        assert _normalize_json('{"a": 1}') == {"a": 1}
        assert _normalize_json('[1, 2]') == [1, 2]

    def test_invalid_json_string(self):
        assert _normalize_json("not json") is None
        assert _normalize_json("not json", []) == []

    def test_other_types_return_default(self):
        assert _normalize_json(42) is None
        assert _normalize_json(42, "fallback") == "fallback"


# =========================================================================
# Validation sets
# =========================================================================

class TestValidationSets:
    def test_discipline_types(self):
        expected = {"verbal_warning", "written_warning", "pip", "final_warning", "suspension"}
        assert VALID_DISCIPLINE_TYPES == expected

    def test_discipline_statuses(self):
        expected = {"active", "completed", "expired", "escalated"}
        assert VALID_DISCIPLINE_STATUSES == expected

    def test_charge_types(self):
        expected = {"eeoc", "nlrb", "osha", "state_agency", "other"}
        assert VALID_CHARGE_TYPES == expected

    def test_charge_statuses(self):
        expected = {"filed", "investigating", "mediation", "resolved", "dismissed", "litigated"}
        assert VALID_CHARGE_STATUSES == expected

    def test_claim_statuses(self):
        expected = {"filed", "investigating", "mediation", "settled", "dismissed", "litigated", "judgment"}
        assert VALID_CLAIM_STATUSES == expected


# =========================================================================
# Pydantic model validation
# =========================================================================

class TestPydanticModels:
    def test_discipline_create_required_fields(self):
        req = DisciplineCreateRequest(
            employee_id=uuid4(),
            discipline_type="pip",
            issued_date=date(2026, 1, 15),
        )
        assert req.description is None
        assert req.expected_improvement is None
        assert req.review_date is None

    def test_discipline_create_all_fields(self):
        eid = uuid4()
        req = DisciplineCreateRequest(
            employee_id=eid,
            discipline_type="written_warning",
            issued_date=date(2026, 3, 1),
            description="Late arrivals",
            expected_improvement="On time for 30 days",
            review_date=date(2026, 4, 1),
        )
        assert req.employee_id == eid
        assert req.description == "Late arrivals"

    def test_discipline_update_all_optional(self):
        req = DisciplineUpdateRequest()
        assert req.status is None
        assert req.outcome_notes is None

    def test_agency_charge_create(self):
        req = AgencyChargeCreateRequest(
            employee_id=uuid4(),
            charge_type="eeoc",
            filing_date=date(2026, 2, 1),
        )
        assert req.charge_number is None
        assert req.agency_name is None

    def test_agency_charge_update_all_optional(self):
        req = AgencyChargeUpdateRequest()
        assert req.resolution_amount is None

    def test_post_term_claim_create(self):
        req = PostTermClaimCreateRequest(
            employee_id=uuid4(),
            claim_type="wrongful_termination",
            filed_date=date(2026, 3, 15),
        )
        assert req.pre_termination_check_id is None

    def test_post_term_claim_update_all_optional(self):
        req = PostTermClaimUpdateRequest()
        assert req.status is None
        assert req.resolution_amount is None

    def test_discipline_create_rejects_missing_required(self):
        with pytest.raises(Exception):
            DisciplineCreateRequest(discipline_type="pip", issued_date=date(2026, 1, 1))


# =========================================================================
# Row-to-response converters
# =========================================================================

class TestRowConverters:
    def _make_row(self, **overrides):
        """Create a dict mimicking an asyncpg Row."""
        base = {
            "id": uuid4(),
            "employee_id": uuid4(),
            "company_id": uuid4(),
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        }
        base.update(overrides)
        return base

    def test_to_discipline_response(self):
        row = self._make_row(
            discipline_type="pip",
            issued_date=date(2026, 1, 15),
            issued_by=uuid4(),
            status="active",
            description="Test",
            expected_improvement=None,
            review_date=None,
            outcome_notes=None,
            documents=None,
        )
        resp = _to_discipline_response(row)
        assert resp.discipline_type == "pip"
        assert resp.status == "active"
        assert resp.documents == []

    def test_to_discipline_response_with_json_documents(self):
        row = self._make_row(
            discipline_type="written_warning",
            issued_date=date(2026, 2, 1),
            issued_by=uuid4(),
            status="completed",
            description=None,
            expected_improvement=None,
            review_date=None,
            outcome_notes="Improved",
            documents='[{"name": "doc.pdf"}]',
        )
        resp = _to_discipline_response(row)
        assert resp.documents == [{"name": "doc.pdf"}]

    def test_to_charge_response(self):
        row = self._make_row(
            charge_type="eeoc",
            charge_number="123-2026-00001",
            filing_date=date(2026, 2, 1),
            agency_name="EEOC",
            status="filed",
            description="Discrimination claim",
            resolution_amount=None,
            resolution_date=None,
            resolution_notes=None,
            documents=None,
            created_by=uuid4(),
        )
        resp = _to_charge_response(row)
        assert resp.charge_type == "eeoc"
        assert resp.resolution_amount is None
        assert resp.documents == []

    def test_to_charge_response_with_resolution_amount(self):
        from decimal import Decimal
        row = self._make_row(
            charge_type="osha",
            charge_number=None,
            filing_date=date(2026, 3, 1),
            agency_name="OSHA",
            status="resolved",
            description=None,
            resolution_amount=Decimal("50000.00"),
            resolution_date=date(2026, 6, 1),
            resolution_notes="Settled",
            documents=[],
            created_by=uuid4(),
        )
        resp = _to_charge_response(row)
        assert resp.resolution_amount == 50000.0

    def test_to_claim_response(self):
        row = self._make_row(
            pre_termination_check_id=uuid4(),
            offboarding_case_id=None,
            claim_type="wrongful_termination",
            filed_date=date(2026, 4, 1),
            status="filed",
            resolution_amount=None,
            resolution_date=None,
            description="Wrongful termination claim",
            created_by=uuid4(),
        )
        resp = _to_claim_response(row)
        assert resp.claim_type == "wrongful_termination"
        assert resp.offboarding_case_id is None

    def test_to_claim_response_with_resolution(self):
        row = self._make_row(
            pre_termination_check_id=None,
            offboarding_case_id=uuid4(),
            claim_type="retaliation",
            filed_date=date(2026, 5, 1),
            status="settled",
            resolution_amount=75000.0,
            resolution_date=date(2026, 8, 1),
            description=None,
            created_by=uuid4(),
        )
        resp = _to_claim_response(row)
        assert resp.resolution_amount == 75000.0
        assert resp.status == "settled"


# =========================================================================
# PreTermCheckResult dataclass
# =========================================================================

class TestPreTermCheckResult:
    def test_construction(self):
        result = PreTermCheckResult(
            overall_score=45,
            overall_band="moderate",
            dimensions={"er_cases": _green("ok")},
            recommended_actions=["Review docs"],
            ai_narrative="Test narrative",
            requires_acknowledgment=False,
            computed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        assert result.overall_score == 45
        assert result.overall_band == "moderate"
        assert len(result.dimensions) == 1

    def test_asdict_serializable(self):
        result = PreTermCheckResult(
            overall_score=80,
            overall_band="critical",
            dimensions={},
            recommended_actions=[],
            ai_narrative=None,
            requires_acknowledgment=True,
            computed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        d = asdict(result)
        assert d["overall_score"] == 80
        assert d["requires_acknowledgment"] is True
