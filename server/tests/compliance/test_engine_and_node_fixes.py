"""Tests for the 2026-07-09 compliance-engine + node-system fixes.

Covers (see MATCHA_WORK_CHAT_AUDIT.md + its supplement):
- ceiling precedence picks the rule's higher jurisdiction, not the most
  general row in the chain
- precedence LEFT JOIN fanout is deduped; specific rules win over blanket
- numeric trigger comparisons coerce strings instead of raising TypeError
- payer-name normalization no longer maps Medicaid programs to Medicare
- the deterministic federal headcount-threshold engine

Pure-function tests only — no DB.
"""

import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

import pytest


def _make_row(
    category: str,
    level: str,
    depth: int,
    numeric_value: Optional[float] = None,
    rule_id: Optional[str] = None,
    precedence_type: Optional[str] = None,
    applies_to_all_children: Optional[bool] = None,
    trigger_conditions: Optional[dict] = None,
    rule_trigger_condition: Optional[dict] = None,
    req_id: Optional[uuid.UUID] = None,
    jurisdiction_id: Optional[uuid.UUID] = None,
    rule_higher_jurisdiction_id: Optional[uuid.UUID] = None,
    rule_lower_jurisdiction_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    return {
        "id": req_id or uuid.uuid4(),
        "jurisdiction_id": jurisdiction_id or uuid.uuid4(),
        "requirement_key": f"{level}_{category}",
        "category": category,
        "category_id": uuid.uuid4(),
        "jurisdiction_level": level,
        "jurisdiction_name": f"Test {level}",
        "jur_level": level,
        "jur_display_name": f"Test {level}",
        "title": f"{level.title()} {category}",
        "description": None,
        "current_value": f"${numeric_value}/hr" if numeric_value else None,
        "numeric_value": Decimal(str(numeric_value)) if numeric_value is not None else None,
        "source_url": None,
        "source_name": None,
        "effective_date": None,
        "rate_type": None,
        "canonical_key": f"test_{level}_{category}",
        "statute_citation": None,
        "req_status": "active",
        "trigger_conditions": trigger_conditions,
        "applicable_entity_types": None,
        "depth": depth,
        "rule_id": rule_id,
        "precedence_type": precedence_type,
        "rule_reasoning_text": "Test reasoning" if rule_id else None,
        "rule_legal_citation": "Test § 1.2.3" if rule_id else None,
        "rule_trigger_condition": rule_trigger_condition,
        "applies_to_all_children": applies_to_all_children,
        "rule_higher_jurisdiction_id": rule_higher_jurisdiction_id,
        "rule_lower_jurisdiction_id": rule_lower_jurisdiction_id,
    }


class TestCeilingPrecedence:
    def _resolve(self, rows_by_category, facility_attributes=None):
        from app.core.services.compliance_service import determine_governing_requirement
        return determine_governing_requirement(rows_by_category, facility_attributes)

    def test_ceiling_picks_rules_higher_jurisdiction_not_federal(self):
        """A 'state caps city' rule must surface the STATE row even when a
        federal row exists in the category (the old code took sorted[-1])."""
        rule_id = str(uuid.uuid4())
        state_jur = uuid.uuid4()
        rows = {
            "sick_leave": [
                _make_row("sick_leave", "city", 0, numeric_value=72,
                          rule_id=rule_id, precedence_type="ceiling",
                          applies_to_all_children=True,
                          rule_higher_jurisdiction_id=state_jur),
                _make_row("sick_leave", "state", 1, numeric_value=40,
                          jurisdiction_id=state_jur,
                          rule_id=rule_id, precedence_type="ceiling",
                          applies_to_all_children=True,
                          rule_higher_jurisdiction_id=state_jur),
                _make_row("sick_leave", "federal", 2, numeric_value=0,
                          rule_id=rule_id, precedence_type="ceiling",
                          applies_to_all_children=True,
                          rule_higher_jurisdiction_id=state_jur),
            ]
        }
        result = self._resolve(rows)
        assert result[0]["governing_level"] == "state"

    def test_ceiling_without_rule_target_falls_back_to_most_general(self):
        """No rule_higher_jurisdiction_id → legacy behavior (highest depth)."""
        rule_id = str(uuid.uuid4())
        rows = {
            "sick_leave": [
                _make_row("sick_leave", "city", 0, rule_id=rule_id,
                          precedence_type="ceiling", applies_to_all_children=True),
                _make_row("sick_leave", "state", 1, rule_id=rule_id,
                          precedence_type="ceiling", applies_to_all_children=True),
            ]
        }
        result = self._resolve(rows)
        assert result[0]["governing_level"] == "state"


class TestFanoutDedupe:
    def _resolve(self, rows_by_category, facility_attributes=None):
        from app.core.services.compliance_service import determine_governing_requirement
        return determine_governing_requirement(rows_by_category, facility_attributes)

    def test_duplicate_requirement_rows_from_two_rules_are_deduped(self):
        """Two precedence rules for one category fan the LEFT JOIN out to
        row-per-(requirement × rule). all_levels must dedupe by requirement id
        while still considering every rule candidate."""
        req_city = uuid.uuid4()
        req_state = uuid.uuid4()
        lower_jur = uuid.uuid4()
        blanket = str(uuid.uuid4())
        specific = str(uuid.uuid4())
        common = dict(category="minimum_wage")

        def city(rule_id, ptype, blanket_flag, lower=None):
            return _make_row(
                "minimum_wage", "city", 0, numeric_value=18.0, req_id=req_city,
                jurisdiction_id=lower_jur, rule_id=rule_id, precedence_type=ptype,
                applies_to_all_children=blanket_flag,
                rule_lower_jurisdiction_id=lower,
            )

        def state(rule_id, ptype, blanket_flag, lower=None):
            return _make_row(
                "minimum_wage", "state", 1, numeric_value=16.0, req_id=req_state,
                rule_id=rule_id, precedence_type=ptype,
                applies_to_all_children=blanket_flag,
                rule_lower_jurisdiction_id=lower,
            )

        rows = {
            "minimum_wage": [
                city(blanket, "ceiling", True),
                city(specific, "floor", False, lower=lower_jur),
                state(blanket, "ceiling", True),
                state(specific, "floor", False, lower=lower_jur),
            ]
        }
        result = self._resolve(rows)
        item = result[0]
        # Deduped: two requirements, not four fanned rows
        assert len(item["all_levels"]) == 2
        # Specific rule (floor) beat the blanket (ceiling)
        assert item["precedence_type"] == "floor"
        # Floor → highest numeric value governs
        assert float(item["governing_requirement"]["numeric_value"]) == 18.0


class TestTriggerCoercion:
    def _eval(self, cond, attrs):
        from app.core.services.compliance_service import evaluate_trigger_conditions
        return evaluate_trigger_conditions(cond, attrs)

    def test_string_attr_vs_numeric_trigger_coerces(self):
        cond = {"type": "attribute", "key": "bed_count", "operator": "gte", "value": 100}
        assert self._eval(cond, {"bed_count": "120"}) is True
        assert self._eval(cond, {"bed_count": "80"}) is False

    def test_uncoercible_string_degrades_to_false_not_typeerror(self):
        cond = {"type": "attribute", "key": "bed_count", "operator": "gt", "value": 100}
        assert self._eval(cond, {"bed_count": "lots"}) is False

    def test_numeric_string_trigger_value(self):
        cond = {"type": "attribute", "key": "bed_count", "operator": "lt", "value": "100"}
        assert self._eval(cond, {"bed_count": 50}) is True


class TestPayerNormalization:
    def test_medicaid_programs_not_mapped_to_medicare(self):
        from app.core.services.payer_policy_rag import normalize_payer_names
        out = set(normalize_payer_names(["medicare", "medi_cal", "medicaid_other"]))
        assert out == {"Medicare", "Medi-Cal", "Medicaid"}

    def test_unknown_payer_title_cases(self):
        from app.core.services.payer_policy_rag import normalize_payer_names
        assert normalize_payer_names(["aetna"]) == ["Aetna"]

    def test_contract_keys_round_trip(self):
        from app.core.services.payer_policy_rag import contract_keys_for_display_names
        keys = set(contract_keys_for_display_names(["Medi-Cal", "Medicare"]))
        assert "medi_cal" in keys
        assert "medicare" in keys
        assert "medicaid_other" not in keys


class TestThresholdEngine:
    def test_large_company_thresholds(self):
        from app.matcha.services.matcha_work_node import compute_threshold_status
        statuses = {s["name"]: s for s in compute_threshold_status(612)}
        assert statuses["WARN Act (plant closings & mass layoffs)"]["applies"] is True
        assert statuses["FMLA (family & medical leave)"]["applies"] is True

    def test_boundary_at_fifty(self):
        from app.matcha.services.matcha_work_node import compute_threshold_status
        statuses = {s["name"]: s for s in compute_threshold_status(50)}
        assert statuses["FMLA (family & medical leave)"]["applies"] is True
        assert statuses["WARN Act (plant closings & mass layoffs)"]["applies"] is False
        assert statuses["EEO-1 reporting"]["applies"] is False

    def test_small_company(self):
        from app.matcha.services.matcha_work_node import compute_threshold_status
        statuses = compute_threshold_status(10)
        assert all(not s["applies"] for s in statuses)

    def test_fmla_marked_directional(self):
        from app.matcha.services.matcha_work_node import compute_threshold_status
        statuses = {s["name"]: s for s in compute_threshold_status(200)}
        assert statuses["FMLA (family & medical leave)"]["directional"] is True
        assert statuses["Title VII / ADA / GINA (anti-discrimination)"]["directional"] is False
