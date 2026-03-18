"""
PostgreSQL ENUM types for compliance schema.

These are Python enums that map to PostgreSQL ENUM types via SQLAlchemy.
The actual PG ENUMs are created in Migration 1.
"""
import enum


class JurisdictionLevel(str, enum.Enum):
    federal = "federal"
    state = "state"
    county = "county"
    city = "city"
    special_district = "special_district"
    regulatory_body = "regulatory_body"


class PrecedenceType(str, enum.Enum):
    floor = "floor"
    ceiling = "ceiling"
    supersede = "supersede"
    additive = "additive"


class PrecedenceRuleStatus(str, enum.Enum):
    active = "active"
    pending_review = "pending_review"
    repealed = "repealed"


class RequirementStatus(str, enum.Enum):
    active = "active"
    pending = "pending"
    repealed = "repealed"
    superseded = "superseded"
    under_review = "under_review"


class SourceTier(str, enum.Enum):
    tier_1_government = "tier_1_government"
    tier_2_official_secondary = "tier_2_official_secondary"
    tier_3_aggregator = "tier_3_aggregator"


class ChangeSource(str, enum.Enum):
    ai_fetch = "ai_fetch"
    manual_review = "manual_review"
    legislative_update = "legislative_update"
    system_migration = "system_migration"


class EmployeeJurisdictionRelType(str, enum.Enum):
    licensed_in = "licensed_in"
    works_at = "works_at"
    telehealth_coverage = "telehealth_coverage"
    historical = "historical"


class CategoryDomain(str, enum.Enum):
    labor = "labor"
    privacy = "privacy"
    clinical = "clinical"
    billing = "billing"
    licensing = "licensing"
    safety = "safety"
    reporting = "reporting"
    emergency = "emergency"
    corporate_integrity = "corporate_integrity"


class GovernanceSource(str, enum.Enum):
    precedence_rule = "precedence_rule"
    default_local = "default_local"
    not_evaluated = "not_evaluated"
