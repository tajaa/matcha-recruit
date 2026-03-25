"""
ORM package — exports Base and all models.

SQLAlchemy is used ONLY for schema definition and Alembic migration
generation. All runtime queries use the existing asyncpg pool.
"""
from .base import Base, TimestampMixin
from .compliance import ComplianceRequirement
from .employee import EmployeeJurisdiction
from .enums import (
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
from .jurisdiction import ComplianceCategory, Jurisdiction, PrecedenceRule
from .key_definition import (
    RegulationKeyDefinition,
    RegulationKeyDefinitionHistory,
    RepositoryAlert,
)
from .location import BusinessLocation
from .requirement import JurisdictionRequirement, PolicyChangeLog

__all__ = [
    "Base",
    "TimestampMixin",
    # Models
    "BusinessLocation",
    "ComplianceCategory",
    "ComplianceRequirement",
    "EmployeeJurisdiction",
    "Jurisdiction",
    "JurisdictionRequirement",
    "PolicyChangeLog",
    "PrecedenceRule",
    "RegulationKeyDefinition",
    "RegulationKeyDefinitionHistory",
    "RepositoryAlert",
    # Enums
    "CategoryDomain",
    "ChangeSource",
    "EmployeeJurisdictionRelType",
    "GovernanceSource",
    "JurisdictionLevel",
    "PrecedenceRuleStatus",
    "PrecedenceType",
    "RequirementStatus",
    "SourceTier",
]
