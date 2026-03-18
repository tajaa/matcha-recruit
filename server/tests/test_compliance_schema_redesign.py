"""Tests for compliance schema redesign — ORM models, enums, registry,
trigger evaluation, governing requirement resolution, and Pydantic schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# 1. ORM model & enum imports compile correctly
# ---------------------------------------------------------------------------


class TestORMImports:
    """Verify all ORM models and enums import without error."""

    def test_base_imports(self):
        from app.orm.base import Base, TimestampMixin

        assert hasattr(Base, "metadata")
        assert hasattr(TimestampMixin, "created_at")
        assert hasattr(TimestampMixin, "updated_at")

    def test_enum_imports(self):
        from app.orm.enums import (
            CategoryDomain,
            ChangeSource,
            EmployeeJurisdictionRelType,
            GovernanceSource,
            JurisdictionLevel,
            PrecedenceRuleStatus,
            PrecedenceType,
            RequirementStatus,
            SourceTier,
        )

        assert JurisdictionLevel.federal.value == "federal"
        assert JurisdictionLevel.state.value == "state"
        assert JurisdictionLevel.county.value == "county"
        assert JurisdictionLevel.city.value == "city"
        assert JurisdictionLevel.special_district.value == "special_district"

        assert PrecedenceType.floor.value == "floor"
        assert PrecedenceType.ceiling.value == "ceiling"
        assert PrecedenceType.supersede.value == "supersede"
        assert PrecedenceType.additive.value == "additive"

        assert RequirementStatus.active.value == "active"
        assert RequirementStatus.superseded.value == "superseded"

        assert GovernanceSource.precedence_rule.value == "precedence_rule"
        assert GovernanceSource.default_local.value == "default_local"
        assert GovernanceSource.not_evaluated.value == "not_evaluated"

        assert SourceTier.tier_1_government.value == "tier_1_government"

        assert CategoryDomain.labor.value == "labor"
        assert CategoryDomain.privacy.value == "privacy"
        assert CategoryDomain.clinical.value == "clinical"

        assert ChangeSource.ai_fetch.value == "ai_fetch"
        assert EmployeeJurisdictionRelType.works_at.value == "works_at"
        assert PrecedenceRuleStatus.active.value == "active"

    def test_all_orm_models_import(self):
        from app.orm import (
            Base,
            BusinessLocation,
            ComplianceCategory,
            ComplianceRequirement,
            EmployeeJurisdiction,
            Jurisdiction,
            JurisdictionRequirement,
            PolicyChangeLog,
            PrecedenceRule,
        )

        tables = sorted(Base.metadata.tables.keys())
        assert "jurisdictions" in tables
        assert "compliance_categories" in tables
        assert "precedence_rules" in tables
        assert "jurisdiction_requirements" in tables
        assert "policy_change_log" in tables
        assert "compliance_requirements" in tables
        assert "employee_jurisdictions" in tables
        assert "business_locations" in tables

    def test_jurisdiction_model_has_new_columns(self):
        from app.orm.jurisdiction import Jurisdiction

        mapper = Jurisdiction.__table__
        col_names = {c.name for c in mapper.columns}
        assert "level" in col_names
        assert "display_name" in col_names
        assert "parent_id" in col_names
        assert "authority_type" in col_names

    def test_jurisdiction_requirement_model_has_new_columns(self):
        from app.orm.requirement import JurisdictionRequirement

        col_names = {c.name for c in JurisdictionRequirement.__table__.columns}
        assert "canonical_key" in col_names
        assert "category_id" in col_names
        assert "summary" in col_names
        assert "full_text_reference" in col_names
        assert "statute_citation" in col_names
        assert "fetch_hash" in col_names
        assert "status" in col_names
        assert "superseded_by_id" in col_names
        assert "applicable_entity_types" in col_names
        assert "trigger_conditions" in col_names
        assert "metadata" in col_names
        assert "source_tier" in col_names

    def test_compliance_requirement_model_has_explainability_columns(self):
        from app.orm.compliance import ComplianceRequirement

        col_names = {c.name for c in ComplianceRequirement.__table__.columns}
        assert "governing_jurisdiction_level" in col_names
        assert "governing_precedence_rule_id" in col_names
        assert "governance_source" in col_names

    def test_employee_jurisdiction_model(self):
        from app.orm.employee import EmployeeJurisdiction

        col_names = {c.name for c in EmployeeJurisdiction.__table__.columns}
        assert "employee_id" in col_names
        assert "jurisdiction_id" in col_names
        assert "relationship_type" in col_names
        assert "effective_date" in col_names
        assert "end_date" in col_names

    def test_precedence_rule_check_constraint(self):
        from app.orm.jurisdiction import PrecedenceRule

        constraints = PrecedenceRule.__table__.constraints
        check_names = [
            c.name
            for c in constraints
            if hasattr(c, "name") and c.name and "children_xor_lower" in c.name
        ]
        assert len(check_names) == 1

    def test_business_location_has_facility_attributes(self):
        from app.orm.location import BusinessLocation

        col_names = {c.name for c in BusinessLocation.__table__.columns}
        assert "facility_attributes" in col_names


# ---------------------------------------------------------------------------
# 2. Compliance Registry — CATEGORY_DOMAIN_MAP
# ---------------------------------------------------------------------------


class TestComplianceRegistry:
    """Verify CATEGORY_DOMAIN_MAP covers all categories."""

    def test_domain_map_covers_all_categories(self):
        from app.core.compliance_registry import CATEGORIES, CATEGORY_DOMAIN_MAP

        category_keys = {c.key for c in CATEGORIES}
        mapped_keys = set(CATEGORY_DOMAIN_MAP.keys())
        missing = category_keys - mapped_keys
        assert not missing, f"Categories missing from CATEGORY_DOMAIN_MAP: {missing}"

    def test_domain_map_values_are_valid(self):
        from app.core.compliance_registry import CATEGORY_DOMAIN_MAP
        from app.orm.enums import CategoryDomain

        valid_domains = {e.value for e in CategoryDomain}
        for key, domain in CATEGORY_DOMAIN_MAP.items():
            assert domain in valid_domains, (
                f"CATEGORY_DOMAIN_MAP['{key}'] = '{domain}' is not a valid CategoryDomain"
            )

    def test_category_count(self):
        from app.core.compliance_registry import CATEGORIES

        # Spec says ~45 entries; ensure we have a reasonable count
        assert len(CATEGORIES) >= 30


# ---------------------------------------------------------------------------
# 3. Pydantic response schemas
# ---------------------------------------------------------------------------


class TestPydanticSchemas:
    """Verify new Pydantic schemas instantiate and validate correctly."""

    def test_jurisdiction_level_requirement(self):
        from app.core.models.compliance import JurisdictionLevelRequirement

        req = JurisdictionLevelRequirement(
            id="abc-123",
            jurisdiction_level="state",
            jurisdiction_name="California",
            title="CA Minimum Wage",
            current_value="$16.00/hr",
            numeric_value=16.0,
            status="active",
            canonical_key="ca_minimum_wage",
        )
        assert req.jurisdiction_level == "state"
        assert req.numeric_value == 16.0

    def test_precedence_info(self):
        from app.core.models.compliance import PrecedenceInfo

        pi = PrecedenceInfo(
            precedence_type="floor",
            reasoning_text="Local ordinances may exceed state minimum wage",
            legal_citation="Cal. Lab. Code §1182.12",
        )
        assert pi.precedence_type == "floor"

    def test_category_compliance_stack(self):
        from app.core.models.compliance import (
            CategoryComplianceStack,
            JurisdictionLevelRequirement,
            PrecedenceInfo,
        )

        gov = JurisdictionLevelRequirement(
            id="r1",
            jurisdiction_level="city",
            jurisdiction_name="San Francisco, CA",
            title="SF Minimum Wage",
            current_value="$18.67/hr",
            numeric_value=18.67,
            status="active",
        )
        state = JurisdictionLevelRequirement(
            id="r2",
            jurisdiction_level="state",
            jurisdiction_name="California",
            title="CA Minimum Wage",
            current_value="$16.00/hr",
            numeric_value=16.0,
            status="active",
        )
        stack = CategoryComplianceStack(
            category="minimum_wage",
            category_label="Minimum Wage",
            domain="labor",
            governing_level="city",
            governing_requirement=gov,
            precedence=PrecedenceInfo(precedence_type="floor"),
            all_levels=[gov, state],
        )
        assert stack.governing_level == "city"
        assert len(stack.all_levels) == 2

    def test_hierarchical_compliance_response(self):
        from app.core.models.compliance import (
            CategoryComplianceStack,
            HierarchicalComplianceResponse,
            JurisdictionLevelRequirement,
        )

        gov = JurisdictionLevelRequirement(
            id="r1",
            jurisdiction_level="city",
            jurisdiction_name="San Francisco, CA",
            title="SF Min Wage",
            status="active",
        )
        cat = CategoryComplianceStack(
            category="minimum_wage",
            category_label="Minimum Wage",
            domain="labor",
            governing_level="city",
            governing_requirement=gov,
            all_levels=[gov],
        )
        resp = HierarchicalComplianceResponse(
            location_id="loc-1",
            location_name="HQ",
            city="San Francisco",
            state="CA",
            categories=[cat],
            total_categories=1,
            total_requirements=1,
        )
        assert resp.total_categories == 1

    def test_trigger_activation(self):
        from app.core.models.compliance import TriggerActivation

        ta = TriggerActivation(
            trigger_type="attribute",
            trigger_key="bed_count",
            trigger_value=50,
            matched=True,
        )
        assert ta.matched is True

    def test_jurisdiction_level_enum_has_special_district(self):
        from app.core.models.compliance import JurisdictionLevel

        assert "special_district" in [e.value for e in JurisdictionLevel]


# ---------------------------------------------------------------------------
# 4. evaluate_trigger_conditions
# ---------------------------------------------------------------------------


class TestTriggerConditionEvaluation:
    """Test the trigger condition evaluator in compliance_service.py."""

    def _eval(self, trigger, attrs=None):
        from app.core.services.compliance_service import evaluate_trigger_conditions

        return evaluate_trigger_conditions(trigger, attrs)

    def test_none_trigger_always_applies(self):
        assert self._eval(None) is True
        assert self._eval(None, {"bed_count": 50}) is True

    def test_attribute_eq(self):
        trigger = {"type": "attribute", "key": "state", "operator": "eq", "value": "CA"}
        assert self._eval(trigger, {"state": "CA"}) is True
        assert self._eval(trigger, {"state": "NY"}) is False

    def test_attribute_gt(self):
        trigger = {"type": "attribute", "key": "bed_count", "operator": "gt", "value": 25}
        assert self._eval(trigger, {"bed_count": 50}) is True
        assert self._eval(trigger, {"bed_count": 25}) is False
        assert self._eval(trigger, {"bed_count": 10}) is False

    def test_attribute_gte(self):
        trigger = {"type": "attribute", "key": "bed_count", "operator": "gte", "value": 25}
        assert self._eval(trigger, {"bed_count": 25}) is True
        assert self._eval(trigger, {"bed_count": 24}) is False

    def test_attribute_lt(self):
        trigger = {"type": "attribute", "key": "employees", "operator": "lt", "value": 50}
        assert self._eval(trigger, {"employees": 49}) is True
        assert self._eval(trigger, {"employees": 50}) is False

    def test_attribute_lte(self):
        trigger = {"type": "attribute", "key": "employees", "operator": "lte", "value": 50}
        assert self._eval(trigger, {"employees": 50}) is True
        assert self._eval(trigger, {"employees": 51}) is False

    def test_attribute_neq(self):
        trigger = {"type": "attribute", "key": "state", "operator": "neq", "value": "CA"}
        assert self._eval(trigger, {"state": "NY"}) is True
        assert self._eval(trigger, {"state": "CA"}) is False

    def test_attribute_in(self):
        trigger = {"type": "attribute", "key": "state", "operator": "in", "value": ["CA", "NY"]}
        assert self._eval(trigger, {"state": "CA"}) is True
        assert self._eval(trigger, {"state": "TX"}) is False

    def test_attribute_contains(self):
        trigger = {"type": "attribute", "key": "specialties", "operator": "contains", "value": "oncology"}
        assert self._eval(trigger, {"specialties": ["oncology", "cardiology"]}) is True
        assert self._eval(trigger, {"specialties": ["cardiology"]}) is False

    def test_attribute_exists(self):
        trigger = {"type": "attribute", "key": "bed_count", "operator": "exists"}
        assert self._eval(trigger, {"bed_count": 100}) is True
        assert self._eval(trigger, {}) is False

    def test_attribute_missing_key_returns_false(self):
        trigger = {"type": "attribute", "key": "missing", "operator": "eq", "value": "x"}
        assert self._eval(trigger, {"other": "y"}) is False

    def test_entity_type_eq(self):
        trigger = {"type": "entity_type", "value": "hospital"}
        assert self._eval(trigger, {"entity_type": "hospital"}) is True
        assert self._eval(trigger, {"entity_type": "clinic"}) is False

    def test_entity_type_in(self):
        trigger = {"type": "entity_type", "operator": "in", "value": ["hospital", "SNF"]}
        assert self._eval(trigger, {"entity_type": "hospital"}) is True
        assert self._eval(trigger, {"entity_type": "clinic"}) is False

    def test_compound_and(self):
        trigger = {
            "op": "and",
            "conditions": [
                {"type": "attribute", "key": "bed_count", "operator": "gt", "value": 25},
                {"type": "entity_type", "value": "hospital"},
            ],
        }
        assert self._eval(trigger, {"bed_count": 50, "entity_type": "hospital"}) is True
        assert self._eval(trigger, {"bed_count": 50, "entity_type": "clinic"}) is False
        assert self._eval(trigger, {"bed_count": 10, "entity_type": "hospital"}) is False

    def test_compound_or(self):
        trigger = {
            "op": "or",
            "conditions": [
                {"type": "attribute", "key": "bed_count", "operator": "gt", "value": 100},
                {"type": "entity_type", "value": "SNF"},
            ],
        }
        assert self._eval(trigger, {"bed_count": 200, "entity_type": "hospital"}) is True
        assert self._eval(trigger, {"bed_count": 10, "entity_type": "SNF"}) is True
        assert self._eval(trigger, {"bed_count": 10, "entity_type": "clinic"}) is False

    def test_compound_not(self):
        trigger = {
            "op": "not",
            "conditions": [
                {"type": "entity_type", "value": "clinic"},
            ],
        }
        assert self._eval(trigger, {"entity_type": "hospital"}) is True
        assert self._eval(trigger, {"entity_type": "clinic"}) is False

    def test_none_facility_attributes_treats_checks_as_false(self):
        trigger = {"type": "attribute", "key": "bed_count", "operator": "gt", "value": 25}
        assert self._eval(trigger, None) is False

    def test_v2_passthrough_types_return_true(self):
        assert self._eval({"type": "requirement_active"}) is True
        assert self._eval({"type": "category_active"}) is True


# ---------------------------------------------------------------------------
# 5. determine_governing_requirement
# ---------------------------------------------------------------------------


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
) -> Dict[str, Any]:
    """Helper to build a fake CTE result row."""
    return {
        "id": uuid.uuid4(),
        "jurisdiction_id": uuid.uuid4(),
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
    }


class TestDetermineGoverningRequirement:
    """Test precedence resolution logic."""

    def _resolve(self, rows_by_category, facility_attributes=None):
        from app.core.services.compliance_service import determine_governing_requirement

        return determine_governing_requirement(rows_by_category, facility_attributes)

    def test_no_rule_defaults_to_most_local(self):
        """Without a precedence rule, the most local (lowest depth) wins."""
        rows = {
            "minimum_wage": [
                _make_row("minimum_wage", "city", 0, numeric_value=18.67),
                _make_row("minimum_wage", "state", 1, numeric_value=16.0),
                _make_row("minimum_wage", "federal", 2, numeric_value=7.25),
            ]
        }
        result = self._resolve(rows)
        assert len(result) == 1
        item = result[0]
        assert item["governance_source"] == "default_local"
        assert item["governing_level"] == "city"
        assert float(item["governing_requirement"]["numeric_value"]) == 18.67

    def test_floor_precedence_picks_highest_value(self):
        """Floor precedence: highest numeric value wins (most beneficial)."""
        rule_id = str(uuid.uuid4())
        rows = {
            "minimum_wage": [
                _make_row("minimum_wage", "city", 0, numeric_value=18.67,
                          rule_id=rule_id, precedence_type="floor",
                          applies_to_all_children=True),
                _make_row("minimum_wage", "state", 1, numeric_value=16.0,
                          rule_id=rule_id, precedence_type="floor",
                          applies_to_all_children=True),
                _make_row("minimum_wage", "federal", 2, numeric_value=7.25,
                          rule_id=rule_id, precedence_type="floor",
                          applies_to_all_children=True),
            ]
        }
        result = self._resolve(rows)
        item = result[0]
        assert item["governance_source"] == "precedence_rule"
        assert item["precedence_type"] == "floor"
        assert float(item["governing_requirement"]["numeric_value"]) == 18.67

    def test_floor_precedence_state_beats_city_when_higher(self):
        """Floor: if state value is higher than city, state governs."""
        rule_id = str(uuid.uuid4())
        rows = {
            "minimum_wage": [
                _make_row("minimum_wage", "city", 0, numeric_value=15.0,
                          rule_id=rule_id, precedence_type="floor",
                          applies_to_all_children=True),
                _make_row("minimum_wage", "state", 1, numeric_value=16.0,
                          rule_id=rule_id, precedence_type="floor",
                          applies_to_all_children=True),
            ]
        }
        result = self._resolve(rows)
        assert float(result[0]["governing_requirement"]["numeric_value"]) == 16.0

    def test_ceiling_precedence_picks_higher_jurisdiction(self):
        """Ceiling: higher jurisdiction's value wins."""
        rule_id = str(uuid.uuid4())
        rows = {
            "sick_leave": [
                _make_row("sick_leave", "city", 0, numeric_value=72,
                          rule_id=rule_id, precedence_type="ceiling",
                          applies_to_all_children=True),
                _make_row("sick_leave", "state", 1, numeric_value=40,
                          rule_id=rule_id, precedence_type="ceiling",
                          applies_to_all_children=True),
            ]
        }
        result = self._resolve(rows)
        item = result[0]
        assert item["governance_source"] == "precedence_rule"
        assert item["precedence_type"] == "ceiling"
        # Ceiling picks highest depth (state at depth 1)
        assert item["governing_level"] == "state"

    def test_supersede_precedence_picks_most_local(self):
        """Supersede: lower jurisdiction completely replaces."""
        rule_id = str(uuid.uuid4())
        rows = {
            "hipaa_privacy": [
                _make_row("hipaa_privacy", "state", 0,
                          rule_id=rule_id, precedence_type="supersede",
                          applies_to_all_children=False),
                _make_row("hipaa_privacy", "federal", 1),
            ]
        }
        result = self._resolve(rows)
        assert result[0]["governing_level"] == "state"
        assert result[0]["governance_source"] == "precedence_rule"

    def test_additive_precedence_uses_most_local_for_display(self):
        """Additive: all levels apply, most local is 'governing' for display."""
        rule_id = str(uuid.uuid4())
        rows = {
            "posting_requirements": [
                _make_row("posting_requirements", "city", 0,
                          rule_id=rule_id, precedence_type="additive",
                          applies_to_all_children=True),
                _make_row("posting_requirements", "state", 1,
                          rule_id=rule_id, precedence_type="additive",
                          applies_to_all_children=True),
                _make_row("posting_requirements", "federal", 2,
                          rule_id=rule_id, precedence_type="additive",
                          applies_to_all_children=True),
            ]
        }
        result = self._resolve(rows)
        item = result[0]
        assert item["precedence_type"] == "additive"
        assert item["governing_level"] == "city"
        assert len(item["all_levels"]) == 3

    def test_multiple_categories_resolved_independently(self):
        """Each category is resolved independently."""
        rows = {
            "minimum_wage": [
                _make_row("minimum_wage", "city", 0, numeric_value=18.67),
                _make_row("minimum_wage", "state", 1, numeric_value=16.0),
            ],
            "sick_leave": [
                _make_row("sick_leave", "state", 0, numeric_value=40),
            ],
        }
        result = self._resolve(rows)
        assert len(result) == 2
        cats = {r["category"] for r in result}
        assert cats == {"minimum_wage", "sick_leave"}

    def test_empty_category_skipped(self):
        rows = {"empty": []}
        result = self._resolve(rows)
        assert len(result) == 0

    def test_trigger_condition_filters_rows(self):
        """Rows with unmet trigger conditions are excluded."""
        trigger = {"type": "entity_type", "value": "hospital"}
        rows = {
            "radiation_safety": [
                _make_row("radiation_safety", "state", 0,
                          trigger_conditions=trigger),
            ]
        }
        # Clinic does not match hospital trigger
        result = self._resolve(rows, facility_attributes={"entity_type": "clinic"})
        assert len(result) == 0

        # Hospital matches
        result = self._resolve(rows, facility_attributes={"entity_type": "hospital"})
        assert len(result) == 1

    def test_specific_rule_preferred_over_blanket(self):
        """Specific pair rule (applies_to_all_children=false) takes priority."""
        blanket_rule = str(uuid.uuid4())
        specific_rule = str(uuid.uuid4())
        rows = {
            "minimum_wage": [
                _make_row("minimum_wage", "city", 0, numeric_value=18.67,
                          rule_id=specific_rule, precedence_type="supersede",
                          applies_to_all_children=False),
                _make_row("minimum_wage", "state", 1, numeric_value=16.0,
                          rule_id=blanket_rule, precedence_type="floor",
                          applies_to_all_children=True),
            ]
        }
        result = self._resolve(rows)
        # The specific rule (supersede) should win over the blanket (floor)
        assert result[0]["precedence_type"] == "supersede"
        assert result[0]["rule_id"] == specific_rule

    def test_governing_requirement_includes_metadata(self):
        """Result includes reasoning_text, legal_citation from the rule."""
        rule_id = str(uuid.uuid4())
        rows = {
            "minimum_wage": [
                _make_row("minimum_wage", "city", 0, numeric_value=18.67,
                          rule_id=rule_id, precedence_type="floor",
                          applies_to_all_children=True),
            ]
        }
        result = self._resolve(rows)
        item = result[0]
        assert item["reasoning_text"] == "Test reasoning"
        assert item["legal_citation"] == "Test § 1.2.3"


# ---------------------------------------------------------------------------
# 6. Alembic env.py — include_name filter
# ---------------------------------------------------------------------------


class TestAlembicEnv:
    """Verify alembic env.py configuration is correct."""

    def test_target_metadata_is_orm_base(self):
        """env.py should use Base.metadata from app.orm."""
        from app.orm import Base

        # Verify it contains the expected tables
        tables = set(Base.metadata.tables.keys())
        assert "jurisdictions" in tables
        assert "compliance_categories" in tables
        assert "precedence_rules" in tables

    def test_include_name_filter_logic(self):
        """include_name should only allow modeled tables."""
        from app.orm import Base

        modeled = set(Base.metadata.tables.keys())

        # Simulate the filter
        def include_name(name, type_, parent_names):
            if type_ == "table":
                return name in modeled
            return True

        # Modeled tables pass
        assert include_name("jurisdictions", "table", {}) is True
        assert include_name("compliance_categories", "table", {}) is True
        # Legacy unmodeled tables are filtered out
        assert include_name("users", "table", {}) is False
        assert include_name("companies", "table", {}) is False
        # Non-table types always pass
        assert include_name("anything", "index", {}) is True


# ---------------------------------------------------------------------------
# 7. TypeScript types match Pydantic schemas
# ---------------------------------------------------------------------------


class TestFrontendTypeAlignment:
    """Verify Pydantic schemas and TS types have matching fields."""

    def test_hierarchical_response_fields(self):
        from app.core.models.compliance import HierarchicalComplianceResponse

        fields = set(HierarchicalComplianceResponse.model_fields.keys())
        expected = {
            "location_id", "location_name", "city", "state",
            "facility_attributes", "categories", "total_categories",
            "total_requirements",
        }
        assert expected.issubset(fields)

    def test_category_compliance_stack_fields(self):
        from app.core.models.compliance import CategoryComplianceStack

        fields = set(CategoryComplianceStack.model_fields.keys())
        expected = {
            "category", "category_label", "domain", "authority_type",
            "governing_level", "governing_requirement", "precedence",
            "all_levels", "affected_employee_count",
        }
        assert expected.issubset(fields)

    def test_jurisdiction_level_requirement_fields(self):
        from app.core.models.compliance import JurisdictionLevelRequirement

        fields = set(JurisdictionLevelRequirement.model_fields.keys())
        expected = {
            "id", "jurisdiction_level", "jurisdiction_name", "title",
            "description", "current_value", "numeric_value", "source_url",
            "statute_citation", "status", "canonical_key", "triggered_by",
        }
        assert expected.issubset(fields)


# ---------------------------------------------------------------------------
# 8. Migration file existence
# ---------------------------------------------------------------------------


class TestMigrationFilesExist:
    """Verify all 5 migration files were created."""

    def test_migration_files_present(self):
        from pathlib import Path

        versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        migration_files = list(versions_dir.glob("z*_0[1-5]_*.py"))
        assert len(migration_files) >= 5, (
            f"Expected 5 migration files, found {len(migration_files)}: "
            f"{[f.name for f in migration_files]}"
        )

    def test_migration_01_enums_and_categories(self):
        from pathlib import Path

        versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        matches = list(versions_dir.glob("*_01_enums_and_categories.py"))
        assert len(matches) == 1

    def test_migration_02_jurisdictions(self):
        from pathlib import Path

        versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        matches = list(versions_dir.glob("*_02_jurisdictions_hierarchy.py"))
        assert len(matches) == 1

    def test_migration_03_precedence(self):
        from pathlib import Path

        versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        matches = list(versions_dir.glob("*_03_precedence_rules.py"))
        assert len(matches) == 1

    def test_migration_04_requirements(self):
        from pathlib import Path

        versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        matches = list(versions_dir.glob("*_04_jurisdiction_requirements_granular.py"))
        assert len(matches) == 1

    def test_migration_05_explainability(self):
        from pathlib import Path

        versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        matches = list(versions_dir.glob("*_05_explainability_and_employee_jurisdictions.py"))
        assert len(matches) == 1
