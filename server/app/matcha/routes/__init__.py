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
from .broker_portfolio import router as broker_portfolio_router
from .broker_external import router as broker_external_router
from .broker_submission import router as broker_submission_router
from .broker_loss_runs import router as broker_loss_runs_router
from .workforce_compliance import router as workforce_compliance_router
from .risk_profile import router as risk_profile_router
from .resident_care import router as resident_care_router
from .controls_evidence import router as controls_evidence_router
from .legal_defense import router as legal_defense_router, public_router as legal_defense_public_router
from .limit_adequacy import router as limit_adequacy_router
from .property import router as property_router
from .driver_risk import router as driver_risk_router
from .ir_onboarding import router as ir_onboarding_router
from .matcha_x_onboarding import router as matcha_x_onboarding_router
from .ir_surveys import router as ir_surveys_router
from .accommodations import router as accommodations_router
from .dashboard import router as dashboard_router
from .brokers import router as brokers_router
from .fractional_hr import router as fractional_hr_router
from .provisioning import router as provisioning_router
from .matcha_work import router as matcha_work_router, public_router as matcha_work_public_router, presence_router as matcha_work_presence_router
from .journals import router as journals_router
from .productivity import router as productivity_router
from .billing import router as matcha_work_billing_router, admin_router as matcha_work_billing_admin_router
from .notifications import router as mw_notifications_router
from .risk_assessment import router as risk_assessment_router
from .pre_termination import router as pre_termination_router
from .discipline import router as discipline_router, public_router as discipline_public_router
from .flight_risk import router as flight_risk_router
from .inbound_email import router as anonymous_report_router
from .external_intake import router as external_intake_router
from .wc_rates_admin import router as wc_rates_admin_router
from .training import router as training_router
from .i9 import router as i9_router
from .cobra import router as cobra_router
from .benefits import router as benefits_router
from .separation import router as separation_router
from .fake_hris import router as fake_hris_router
from .twilio_webhook import router as twilio_webhook_router
from .labor_relations import router as labor_relations_router
from ..dependencies import require_feature, require_any_feature
from ...core.dependencies import require_admin

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
matcha_router.include_router(ir_onboarding_router, prefix="/ir-onboarding", tags=["ir-onboarding"],
                             dependencies=[Depends(require_feature("incidents"))])
matcha_router.include_router(matcha_x_onboarding_router, prefix="/matcha-x-onboarding",
                             tags=["matcha-x-onboarding"],
                             # Matcha-X reaches this via handbook_audit (always-on
                             # in its overlay); the standalone Matcha Compliance
                             # product reuses the same wizard but only holds the
                             # full `compliance` flag — admit either.
                             dependencies=[Depends(require_any_feature("handbook_audit", "compliance"))])
matcha_router.include_router(ir_surveys_router, prefix="/ir/surveys", tags=["ir-surveys"],
                             dependencies=[Depends(require_feature("incidents"))])
matcha_router.include_router(accommodations_router, prefix="/accommodations", tags=["accommodations"],
                             dependencies=[Depends(require_feature("accommodations"))])
# Labor Relations — union / CBA admin (Pro-bundled). CBA store + clause library
# + grievance workflow live under /labor.
matcha_router.include_router(labor_relations_router, prefix="/labor", tags=["labor-relations"],
                             dependencies=[Depends(require_feature("labor_relations"))])
matcha_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
matcha_router.include_router(brokers_router, prefix="/brokers", tags=["brokers"])
# Fractional HR — internal master-admin engagement tooling (admin-gated, not feature-flagged)
matcha_router.include_router(fractional_hr_router, prefix="/fractional-hr", tags=["fractional-hr"],
                             dependencies=[Depends(require_admin)])
matcha_router.include_router(broker_portfolio_router, prefix="/broker", tags=["broker-portfolio"])
# Off-platform broker clients (Broker Pro) — each endpoint is require_broker_pro gated.
matcha_router.include_router(broker_external_router, prefix="/broker", tags=["broker-external"])
# Submission packet + AI coverage-gap (outward layer) — gated per-endpoint.
matcha_router.include_router(broker_submission_router, prefix="/broker", tags=["broker-submission"])
# Loss-run triangulation / development — gated per-endpoint (require_broker / _pro).
matcha_router.include_router(broker_loss_runs_router, prefix="/broker", tags=["broker-loss-runs"])
# Workforce Compliance — business-first EPL risk trackers (pay transparency, AI-audit, biometric).
matcha_router.include_router(workforce_compliance_router, prefix="/workforce-compliance",
                             tags=["workforce-compliance"],
                             dependencies=[Depends(require_feature("workforce_compliance"))])
matcha_router.include_router(risk_profile_router, prefix="/risk-profile", tags=["risk-profile"],
                             dependencies=[Depends(require_feature("risk_profile"))])
matcha_router.include_router(resident_care_router, prefix="/resident-care", tags=["resident-care"],
                             dependencies=[Depends(require_feature("resident_care"))])
matcha_router.include_router(controls_evidence_router, prefix="/controls-evidence", tags=["controls-evidence"],
                             dependencies=[Depends(require_feature("controls_evidence"))])
matcha_router.include_router(legal_defense_router, prefix="/legal-pilot", tags=["legal-pilot"],
                             dependencies=[Depends(require_feature("legal_defense"))])
matcha_router.include_router(limit_adequacy_router, prefix="/limit-adequacy", tags=["limit-adequacy"],
                             dependencies=[Depends(require_feature("limit_adequacy"))])
matcha_router.include_router(property_router, prefix="/property", tags=["property"],
                             dependencies=[Depends(require_feature("property"))])
matcha_router.include_router(driver_risk_router, prefix="/driver-risk", tags=["driver-risk"],
                             dependencies=[Depends(require_feature("driver_risk"))])
matcha_router.include_router(provisioning_router, prefix="/provisioning", tags=["provisioning"])
matcha_router.include_router(
    matcha_work_router,
    prefix="/matcha-work",
    tags=["matcha-work"],
    dependencies=[Depends(require_feature("matcha_work"))],
)
matcha_router.include_router(
    journals_router,
    prefix="/matcha-work",
    tags=["matcha-work-journals"],
    dependencies=[Depends(require_feature("matcha_work"))],
)
matcha_router.include_router(
    productivity_router,
    prefix="/matcha-work",
    tags=["matcha-work-productivity"],
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
    discipline_router,
    prefix="/discipline",
    tags=["discipline"],
    dependencies=[Depends(require_feature("discipline"))],
)
matcha_router.include_router(
    discipline_public_router,
    prefix="/discipline",
    tags=["discipline-webhook"],
)
matcha_router.include_router(
    flight_risk_router,
    prefix="/flight-risk",
    tags=["flight-risk"],
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
    benefits_router,
    prefix="/benefits",
    tags=["benefits"],
    dependencies=[Depends(require_feature("benefits_admin"))],
)
matcha_router.include_router(
    separation_router,
    prefix="/separation-agreements",
    tags=["separation"],
    dependencies=[Depends(require_feature("separation_agreements"))],
)
# Public anonymous incident reporting — no auth, no feature gate (token-validated internally)
matcha_router.include_router(anonymous_report_router, tags=["anonymous-reporting"])
matcha_router.include_router(legal_defense_public_router, tags=["legal-pilot-public"])
# Public off-platform client-intake — no auth, token-validated internally
matcha_router.include_router(external_intake_router, prefix="/external-intake", tags=["external-intake-public"])
# Admin WC rate-data import (require_admin per-endpoint)
matcha_router.include_router(wc_rates_admin_router, prefix="/admin/wc-rates", tags=["wc-rates-admin"])
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
    "flight_risk_router",
    "training_router",
    "i9_router",
    "cobra_router",
    "separation_router",
    "fake_hris_router",
]
