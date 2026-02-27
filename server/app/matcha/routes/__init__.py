"""Matcha (HR/Recruiting) routes aggregation."""

from fastapi import APIRouter, Depends

from .companies import router as companies_router
from .positions import router as positions_router
from .candidates import router as candidates_router
from .interviews import router as interviews_router
from .employees import router as employees_router, pto_admin_router, leave_admin_router
from .employee_portal import router as employee_portal_router
from .onboarding import router as onboarding_router
from .invitations import router as invitations_router
from .offer_letters import router as offer_letters_router, candidate_router as offer_letters_candidate_router
from .openings import router as openings_router
from .matching import router as matching_router
from .ranking import router as ranking_router
from .er_copilot import router as er_copilot_router
from .ir_incidents import router as ir_incidents_router
from .accommodations import router as accommodations_router
from .job_search import router as job_search_router
from .public_jobs import router as public_jobs_router
from .xp_admin import router as xp_admin_router
from .dashboard import router as dashboard_router
from .brokers import router as brokers_router
from .provisioning import router as provisioning_router
from .reach_out import router as reach_out_router
from .internal_mobility import router as internal_mobility_router
from .matcha_work import router as matcha_work_router, public_router as matcha_work_public_router
from .billing import router as matcha_work_billing_router, admin_router as matcha_work_billing_admin_router
from ..dependencies import require_feature

# Create main Matcha router
matcha_router = APIRouter()

# Mount sub-routers
matcha_router.include_router(companies_router, prefix="/companies", tags=["companies"])
matcha_router.include_router(positions_router, prefix="/positions", tags=["positions"])
matcha_router.include_router(candidates_router, prefix="/candidates", tags=["candidates"])
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
matcha_router.include_router(openings_router, prefix="/openings", tags=["openings"])
matcha_router.include_router(matching_router, tags=["matching"])
matcha_router.include_router(ranking_router, tags=["rankings"])
matcha_router.include_router(er_copilot_router, prefix="/er/cases", tags=["er-copilot"],
                             dependencies=[Depends(require_feature("er_copilot"))])
matcha_router.include_router(ir_incidents_router, prefix="/ir/incidents", tags=["ir-incidents"],
                             dependencies=[Depends(require_feature("incidents"))])
matcha_router.include_router(accommodations_router, prefix="/accommodations", tags=["accommodations"],
                             dependencies=[Depends(require_feature("accommodations"))])
matcha_router.include_router(job_search_router, prefix="/jobs", tags=["job-search"])
matcha_router.include_router(public_jobs_router, prefix="/job-board", tags=["public-jobs"])
matcha_router.include_router(xp_admin_router, tags=["employee-experience"])
matcha_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
matcha_router.include_router(brokers_router, prefix="/brokers", tags=["brokers"])
matcha_router.include_router(provisioning_router, prefix="/provisioning", tags=["provisioning"])
matcha_router.include_router(reach_out_router, tags=["reach-out"])
matcha_router.include_router(
    internal_mobility_router,
    prefix="/internal-mobility",
    tags=["internal-mobility"],
    dependencies=[Depends(require_feature("internal_mobility"))],
)
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

# Export individual routers for backwards compatibility
__all__ = [
    "matcha_router",
    "companies_router",
    "positions_router",
    "candidates_router",
    "interviews_router",
    "employees_router",
    "pto_admin_router",
    "leave_admin_router",
    "employee_portal_router",
    "onboarding_router",
    "invitations_router",
    "offer_letters_router",
    "openings_router",
    "matching_router",
    "ranking_router",
    "er_copilot_router",
    "ir_incidents_router",
    "job_search_router",
    "public_jobs_router",
    "xp_admin_router",
    "dashboard_router",
    "accommodations_router",
    "brokers_router",
    "provisioning_router",
    "internal_mobility_router",
    "matcha_work_router",
    "matcha_work_public_router",
    "matcha_work_billing_router",
]
