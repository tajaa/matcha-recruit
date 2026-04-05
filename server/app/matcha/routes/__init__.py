"""Matcha (HR/Recruiting) routes aggregation."""

from fastapi import APIRouter, Depends

from .companies import router as companies_router
from .interviews import router as interviews_router
from .employees import router as employees_router, pto_admin_router, leave_admin_router
from .employee_portal import router as employee_portal_router
from .onboarding import router as onboarding_router
from .invitations import router as invitations_router
from .offer_letters import router as offer_letters_router, candidate_router as offer_letters_candidate_router
from .er_copilot import router as er_copilot_router, public_router as er_copilot_public_router
from .ir_incidents import router as ir_incidents_router
from .accommodations import router as accommodations_router
from .dashboard import router as dashboard_router
from .brokers import router as brokers_router
from .provisioning import router as provisioning_router
from .matcha_work import router as matcha_work_router, public_router as matcha_work_public_router, presence_router as matcha_work_presence_router
from .billing import router as matcha_work_billing_router, admin_router as matcha_work_billing_admin_router
from .notifications import router as mw_notifications_router
from .risk_assessment import router as risk_assessment_router
from .pre_termination import router as pre_termination_router
from .inbound_email import router as anonymous_report_router
from .training import router as training_router
from .i9 import router as i9_router
from .cobra import router as cobra_router
from .separation import router as separation_router
from .fake_hris import router as fake_hris_router
from .twilio_webhook import router as twilio_webhook_router
from ..dependencies import require_feature

# Create main Matcha router
matcha_router = APIRouter()

# Mount sub-routers
matcha_router.include_router(companies_router, prefix="/companies", tags=["companies"])
matcha_router.include_router(interviews_router, tags=["interviews"])
matcha_router.include_router(employees_router, prefix="/employees", tags=["employees"],
                             dependencies=[Depends(require_feature("employees"))])
matcha_router.include_router(pto_admin_router, prefix="/employees/pto", tags=["pto-admin"],
                             dependencies=[Depends(require_feature("time_off"))])
matcha_router.include_router(leave_admin_router, prefix="/employees/leave", tags=["leave-admin"],
                             dependencies=[Depends(require_feature("time_off"))])
matcha_router.include_router(employee_portal_router, prefix="/v1/portal", tags=["employee-portal"])
matcha_router.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
matcha_router.include_router(invitations_router, prefix="/invitations", tags=["invitations"])
matcha_router.include_router(offer_letters_router, prefix="/offer-letters", tags=["offer-letters"],
                             dependencies=[Depends(require_feature("offer_letters"))])
# Public candidate endpoints — no auth, no feature gate
matcha_router.include_router(offer_letters_candidate_router, prefix="/offer-letters", tags=["offer-letters-public"])
matcha_router.include_router(er_copilot_router, prefix="/er/cases", tags=["er-copilot"],
                             dependencies=[Depends(require_feature("er_copilot"))])
matcha_router.include_router(
    er_copilot_public_router,
    prefix="/shared/er-export",
    tags=["er-export-public"],
)
matcha_router.include_router(ir_incidents_router, prefix="/ir/incidents", tags=["ir-incidents"],
                             dependencies=[Depends(require_feature("incidents"))])
matcha_router.include_router(accommodations_router, prefix="/accommodations", tags=["accommodations"],
                             dependencies=[Depends(require_feature("accommodations"))])
matcha_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
matcha_router.include_router(brokers_router, prefix="/brokers", tags=["brokers"])
matcha_router.include_router(provisioning_router, prefix="/provisioning", tags=["provisioning"])
matcha_router.include_router(
    matcha_work_router,
    prefix="/matcha-work",
    tags=["matcha-work"],
    dependencies=[Depends(require_feature("matcha_work"))],
)
matcha_router.include_router(
    matcha_work_public_router,
    prefix="/matcha-work/public",
    tags=["matcha-work-public"],
)
matcha_router.include_router(
    matcha_work_presence_router,
    prefix="/matcha-work/presence",
    tags=["matcha-work-presence"],
)
matcha_router.include_router(
    matcha_work_billing_router,
    prefix="/matcha-work/billing",
    tags=["matcha-work-billing"],
    dependencies=[Depends(require_feature("matcha_work"))],
)
matcha_router.include_router(
    matcha_work_billing_admin_router,
    prefix="/matcha-work/billing",
    tags=["matcha-work-billing-admin"],
)
matcha_router.include_router(
    mw_notifications_router,
    prefix="/matcha-work",
    tags=["matcha-work-notifications"],
)
matcha_router.include_router(
    risk_assessment_router,
    prefix="/risk-assessment",
    tags=["risk-assessment"],
    dependencies=[Depends(require_feature("risk_assessment"))],
)
matcha_router.include_router(
    pre_termination_router,
    prefix="/pre-termination",
    tags=["pre-termination"],
    dependencies=[Depends(require_feature("employees"))],
)
matcha_router.include_router(
    training_router,
    prefix="/training",
    tags=["training"],
    dependencies=[Depends(require_feature("training"))],
)
matcha_router.include_router(
    i9_router,
    prefix="/i9",
    tags=["i9"],
    dependencies=[Depends(require_feature("i9"))],
)
matcha_router.include_router(
    cobra_router,
    prefix="/cobra",
    tags=["cobra"],
    dependencies=[Depends(require_feature("cobra"))],
)
matcha_router.include_router(
    separation_router,
    prefix="/separation-agreements",
    tags=["separation"],
    dependencies=[Depends(require_feature("separation_agreements"))],
)
# Public anonymous incident reporting — no auth, no feature gate (token-validated internally)
matcha_router.include_router(anonymous_report_router, tags=["anonymous-reporting"])
# Fake HRIS (simulates ADP Workforce Now API) — no auth gate
matcha_router.include_router(fake_hris_router, prefix="/fake-hris", tags=["fake-hris"])
matcha_router.include_router(twilio_webhook_router, prefix="/twilio", tags=["twilio"])

# Export individual routers for backwards compatibility
__all__ = [
    "matcha_router",
    "companies_router",
    "interviews_router",
    "employees_router",
    "pto_admin_router",
    "leave_admin_router",
    "employee_portal_router",
    "onboarding_router",
    "invitations_router",
    "offer_letters_router",
    "er_copilot_router",
    "er_copilot_public_router",
    "ir_incidents_router",
    "dashboard_router",
    "accommodations_router",
    "brokers_router",
    "provisioning_router",
    "matcha_work_router",
    "matcha_work_public_router",
    "matcha_work_billing_router",
    "pre_termination_router",
    "training_router",
    "i9_router",
    "cobra_router",
    "separation_router",
    "fake_hris_router",
]
