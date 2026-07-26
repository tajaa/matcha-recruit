"""
Compliance Registry — single source of truth for all compliance categories,
regulations, research prompts, and category aliases.

Every category, regulation, research prompt and alias lives here.
Other modules import from this file rather than defining their own lists.
"""
from app.core.compliance_registry._types import ComplianceCategoryDef, RegulationDef  # noqa: F401
from app.core.compliance_registry.severity import (  # noqa: F401
    _SEVERITY_CRITICAL, _SEVERITY_HIGH, SEVERITY_LEVELS, resolve_severity,
)
from app.core.compliance_registry.categories import CATEGORIES, CATEGORY_DOMAIN_MAP  # noqa: F401
from app.core.compliance_registry.regulations import REGULATIONS  # noqa: F401
from app.core.compliance_registry.research_prompts import RESEARCH_PROMPTS  # noqa: F401
from app.core.compliance_registry.aliases import CATEGORY_ALIASES  # noqa: F401
from app.core.compliance_registry.authority_sources import CATEGORY_AUTHORITY_SOURCES  # noqa: F401
from app.core.compliance_registry.derived import (  # noqa: F401
    CATEGORY_MAP, CATEGORY_KEYS,
    LABOR_CATEGORIES, SUPPLEMENTARY_CATEGORIES, HEALTHCARE_CATEGORIES,
    ONCOLOGY_CATEGORIES, MEDICAL_COMPLIANCE_CATEGORIES, LIFE_SCIENCES_CATEGORIES,
    MANUFACTURING_CATEGORIES, SPECIALTY_CATEGORIES, HEALTH_SPECS_CATEGORIES,
    DEFAULT_RESEARCH_CATEGORIES, CATEGORY_LABELS, CATEGORY_SHORT_LABELS, INDUSTRY_TAGS,
    REGULATION_MAP, REGULATIONS_BY_CATEGORY, EXPECTED_REGULATION_KEYS,
    _LABOR_REGULATION_KEYS, _ONCOLOGY_REGULATION_KEYS, _LIFE_SCIENCES_REGULATION_KEYS,
    _MANUFACTURING_REGULATION_KEYS, _EXPANSION_REGULATION_KEYS,
    _HEALTHCARE_EXPANSION_KEYS, _INTERNATIONAL_REGULATION_KEYS,
    _KEY_COUNTRY_SCOPE, _KEY_STATE_SCOPE, _key_applies_to_country, _key_applies_to_state,
)
from app.core.compliance_registry.trigger_profiles import (  # noqa: F401
    TriggerProfileDef, TRIGGER_PROFILES, get_activated_profiles,
)
from app.core.compliance_registry.queries import get_missing_regulations, resolve_weight  # noqa: F401
from app.core.compliance_registry.government_feeds import (  # noqa: F401
    CATEGORY_FEDERAL_REGISTER_AGENCIES, CMS_CATEGORIES, CATEGORY_OPENSTATES_SUBJECTS,
)
