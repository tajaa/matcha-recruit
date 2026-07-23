"""Matcha (HR/Recruiting) routes aggregation."""

from fastapi import APIRouter, Depends

from .companies import router as companies_router
from .interviews import router as interviews_router
from .employees import router as employees_router, pto_admin_router, leave_admin_router
from .employee_portal import router as employee_portal_router
from .portal_ask_hr import router as portal_ask_hr_router
from .employee_lifecycle import (
    accommodations_router,
    cobra_router,
    discipline_router,
    discipline_public_router,
    flight_risk_router,
    i9_router,
    offer_letters_router,
    offer_letters_candidate_router,
    pre_termination_router,
    separation_router,
    training_router,
)
from .work import (
    journals_router,
    mw_notifications_router,
    project_ws_router,
    thread_ws_router,
)
from .integrations import (
    fake_hris_router,
    provisioning_router,
    twilio_webhook_router,
)
from .er_copilot import router as er_copilot_router, public_router as er_copilot_public_router
from .help_assistant import router as help_assistant_router
from .ir_incidents import router as ir_incidents_router
from .employee_schedule import router as employee_schedule_router
from .schedule_intelligence import router as schedule_intelligence_router
from .ir_surveys import router as ir_surveys_router
from .dashboard import router as dashboard_router
from .fractional_hr import router as fractional_hr_router
from .matcha_work import router as matcha_work_router, public_router as matcha_work_public_router, presence_router as matcha_work_presence_router
from .productivity import router as productivity_router
from .billing import router as matcha_work_billing_router, admin_router as matcha_work_billing_admin_router
from .risk_assessment import router as risk_assessment_router
from .wc_rates_admin import router as wc_rates_admin_router
from .benefits import router as benefits_router
from .labor_relations import router as labor_relations_router
from ..dependencies import require_feature, require_any_feature
from ...core.dependencies import require_admin

# Create main Matcha router
from .broker import (
    brokers_router,
    broker_chat_router,
    broker_external_router,
    broker_insurance_router,
    broker_loss_runs_router,
    broker_pilot_router,
    broker_portfolio_router,
    broker_submission_router,
)
from .broker_chat_company import router as broker_chat_company_router
from .insurance import (
    acord_router,
    coi_router,
    controls_evidence_router,
    driver_risk_router,
    insurance_router,
    limit_adequacy_router,
    management_liability_router,
    property_router,
    resident_care_router,
    risk_profile_router,
    tcor_router,
    workforce_compliance_router,
)
from .pilots import (
    analysis_pilot_router,
    handbook_pilot_router,
    legal_defense_router,
    legal_defense_public_router,
)
from .onboarding import (
    onboarding_router,
    invitations_router,
    ir_onboarding_router,
    matcha_x_onboarding_router,
)
from .intake import anonymous_report_router, external_intake_router

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
# Employee "Ask HR" — grounded, citation-gated policy Q&A for employees. Mounted
# under the portal prefix but gated separately (sold apart from the portal).
matcha_router.include_router(portal_ask_hr_router, prefix="/v1/portal/ask-hr", tags=["ask-hr"],
                             dependencies=[Depends(require_feature("ask_hr"))])
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
# In-app per-page help guide — no feature gate: available to every authed
# business tenant; the FE only surfaces it on pages with a pageHelp.ts entry.
matcha_router.include_router(help_assistant_router, prefix="/assistant", tags=["help-assistant"])
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
# Broker Pilot — grounded per-client analysis chat (every endpoint require_broker_pro).
matcha_router.include_router(broker_pilot_router, prefix="/broker", tags=["broker-pilot"])
# Broker carrier hub — quote/present/bind + claims bridge + risk-to-rate (per-endpoint
# require_broker / _pro; carrier data features capability-gated in coterie_service).
matcha_router.include_router(broker_insurance_router, prefix="/broker", tags=["broker-insurance"])
# Broker↔company chat — broker side (require_broker per-endpoint, no feature gate,
# matching the other broker surfaces). Company side is mounted at /broker-chat below.
matcha_router.include_router(broker_chat_router, prefix="/broker", tags=["broker-chat"])
matcha_router.include_router(broker_chat_company_router, prefix="/broker-chat", tags=["broker-chat-company"])
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
matcha_router.include_router(handbook_pilot_router, prefix="/handbook-pilot", tags=["handbook-pilot"],
                             dependencies=[Depends(require_feature("handbook_pilot"))])
matcha_router.include_router(analysis_pilot_router, prefix="/analysis-pilot", tags=["analysis-pilot"],
                             dependencies=[Depends(require_feature("analysis_pilot"))])
matcha_router.include_router(limit_adequacy_router, prefix="/limit-adequacy", tags=["limit-adequacy"],
                             dependencies=[Depends(require_feature("limit_adequacy"))])
matcha_router.include_router(property_router, prefix="/property", tags=["property"],
                             dependencies=[Depends(require_feature("property"))])
matcha_router.include_router(driver_risk_router, prefix="/driver-risk", tags=["driver-risk"],
                             dependencies=[Depends(require_feature("driver_risk"))])
# Employee scheduling — shift builder + templates over the roster (paid add-on).
matcha_router.include_router(employee_schedule_router, prefix="/employee-schedule",
                             tags=["employee-schedule"],
                             dependencies=[Depends(require_feature("employee_schedule"))])
# Schedule Intelligence — analytics over the schedule data (paid add-on). Each
# endpoint checks `employee_schedule` itself rather than double-gating the mount.
matcha_router.include_router(schedule_intelligence_router, prefix="/schedule-intelligence",
                             tags=["schedule-intelligence"],
                             dependencies=[Depends(require_feature("schedule_intelligence"))])
matcha_router.include_router(tcor_router, prefix="/tcor", tags=["tcor"],
                             dependencies=[Depends(require_feature("tcor"))])
matcha_router.include_router(coi_router, prefix="/coi", tags=["coi"],
                             dependencies=[Depends(require_feature("coi_tracking"))])
matcha_router.include_router(insurance_router, prefix="/insurance", tags=["insurance"],
                             dependencies=[Depends(require_feature("carrier_quotes"))])
matcha_router.include_router(management_liability_router, prefix="/management-liability",
                             tags=["management-liability"],
                             dependencies=[Depends(require_feature("do_readiness"))])
matcha_router.include_router(acord_router, prefix="/acord", tags=["acord"],
                             dependencies=[Depends(require_feature("acord_forms"))])
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
    "broker_chat_router",
    "broker_chat_company_router",
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
