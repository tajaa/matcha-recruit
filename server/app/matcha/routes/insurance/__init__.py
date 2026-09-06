"""Insurance / risk-asset surfaces — underwriting-facing risk features, each its own feature flag.

Namespace grouping: each module is an independent router with its own mount + gate in the
parent ``routes/__init__.py``; this package only re-exports them under their historical names.
"""

from .carrier import router as insurance_router
from .acord import router as acord_router
from .coi import router as coi_router
from .controls_evidence import router as controls_evidence_router
from .limit_adequacy import router as limit_adequacy_router
from .management_liability import router as management_liability_router
from .property import router as property_router
from .risk_profile import router as risk_profile_router
from .tcor import router as tcor_router
from .wc_rates_admin import router as wc_rates_admin_router
from .workforce_compliance import router as workforce_compliance_router

__all__ = [
    "insurance_router",
    "acord_router",
    "coi_router",
    "controls_evidence_router",
    "limit_adequacy_router",
    "management_liability_router",
    "property_router",
    "risk_profile_router",
    "tcor_router",
    "wc_rates_admin_router",
    "workforce_compliance_router",
]
