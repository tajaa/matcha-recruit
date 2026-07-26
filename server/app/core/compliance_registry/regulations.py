"""REGULATIONS aggregation — concatenates the per-domain lists in original order."""
from __future__ import annotations

from typing import List

from app.core.compliance_registry._types import RegulationDef
from app.core.compliance_registry.regulations_healthcare import REGULATIONS_HEALTHCARE
from app.core.compliance_registry.regulations_medical_compliance import REGULATIONS_MEDICAL_COMPLIANCE
from app.core.compliance_registry.regulations_medical_specialty import REGULATIONS_MEDICAL_SPECIALTY
from app.core.compliance_registry.regulations_life_sciences import REGULATIONS_LIFE_SCIENCES
from app.core.compliance_registry.regulations_labor import REGULATIONS_LABOR
from app.core.compliance_registry.regulations_supplementary import REGULATIONS_SUPPLEMENTARY
from app.core.compliance_registry.regulations_expansion import REGULATIONS_EXPANSION
from app.core.compliance_registry.regulations_manufacturing import REGULATIONS_MANUFACTURING
from app.core.compliance_registry.regulations_oncology import REGULATIONS_ONCOLOGY

REGULATIONS: List[RegulationDef] = [
    *REGULATIONS_HEALTHCARE,
    *REGULATIONS_MEDICAL_COMPLIANCE,
    *REGULATIONS_MEDICAL_SPECIALTY,
    *REGULATIONS_LIFE_SCIENCES,
    *REGULATIONS_LABOR,
    *REGULATIONS_SUPPLEMENTARY,
    *REGULATIONS_EXPANSION,
    *REGULATIONS_MANUFACTURING,
    *REGULATIONS_ONCOLOGY,
]
