"""Matcha (HR/Recruiting) routes aggregation."""

from fastapi import APIRouter

from .companies import router as companies_router
from .positions import router as positions_router
from .candidates import router as candidates_router
from .interviews import router as interviews_router
from .employees import router as employees_router
from .employee_portal import router as employee_portal_router
from .onboarding import router as onboarding_router
from .invitations import router as invitations_router
from .offer_letters import router as offer_letters_router
from .openings import router as openings_router
from .matching import router as matching_router
from .er_copilot import router as er_copilot_router
from .ir_incidents import router as ir_incidents_router
from .job_search import router as job_search_router
from .public_jobs import router as public_jobs_router
from .xp_admin import router as xp_admin_router

# Create main Matcha router
matcha_router = APIRouter()

# Mount sub-routers
matcha_router.include_router(companies_router, prefix="/companies", tags=["companies"])
matcha_router.include_router(positions_router, prefix="/positions", tags=["positions"])
matcha_router.include_router(candidates_router, prefix="/candidates", tags=["candidates"])
matcha_router.include_router(interviews_router, tags=["interviews"])
matcha_router.include_router(employees_router, prefix="/employees", tags=["employees"])
matcha_router.include_router(employee_portal_router, prefix="/v1/portal", tags=["employee-portal"])
matcha_router.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
matcha_router.include_router(invitations_router, prefix="/invitations", tags=["invitations"])
matcha_router.include_router(offer_letters_router, prefix="/offer-letters", tags=["offer-letters"])
matcha_router.include_router(openings_router, prefix="/openings", tags=["openings"])
matcha_router.include_router(matching_router, tags=["matching"])
matcha_router.include_router(er_copilot_router, prefix="/er/cases", tags=["er-copilot"])
matcha_router.include_router(ir_incidents_router, prefix="/ir/incidents", tags=["ir-incidents"])
matcha_router.include_router(job_search_router, prefix="/jobs", tags=["job-search"])
matcha_router.include_router(public_jobs_router, prefix="/job-board", tags=["public-jobs"])
matcha_router.include_router(xp_admin_router, tags=["employee-experience"])

# Export individual routers for backwards compatibility
__all__ = [
    "matcha_router",
    "companies_router",
    "positions_router",
    "candidates_router",
    "interviews_router",
    "employees_router",
    "employee_portal_router",
    "onboarding_router",
    "invitations_router",
    "offer_letters_router",
    "openings_router",
    "matching_router",
    "er_copilot_router",
    "ir_incidents_router",
    "job_search_router",
    "public_jobs_router",
    "xp_admin_router",
]
