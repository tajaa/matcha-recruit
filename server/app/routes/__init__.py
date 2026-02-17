"""
DEPRECATED: Routes have been reorganized into domains.

- Core routes: server/app/core/routes/
- Matcha (HR/Recruiting) routes: server/app/matcha/routes/

These re-exports are provided for backward compatibility.
"""

# Core routes
from ..core.routes import (
    auth_router,
    blog_router,
    policies_router,
    handbooks_router,
    public_signatures_router,
    compliance_router,
    bulk_import_router,
    chat_router,
    chat_ws_router,
    contact_router,
    projects_router,
    outreach_router,
    leads_agent_router,
)

# Matcha routes
from ..matcha.routes import (
    companies_router,
    positions_router,
    candidates_router,
    interviews_router,
    employees_router,
    employee_portal_router,
    onboarding_router,
    invitations_router,
    offer_letters_router,
    openings_router,
    matching_router,
    er_copilot_router,
    ir_incidents_router,
    job_search_router,
    public_jobs_router,
    provisioning_router,
)

__all__ = [
    # Core
    "auth_router",
    "blog_router",
    "policies_router",
    "handbooks_router",
    "public_signatures_router",
    "compliance_router",
    "bulk_import_router",
    "chat_router",
    "chat_ws_router",
    "contact_router",
    "projects_router",
    "outreach_router",
    "leads_agent_router",
    # Matcha
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
    "provisioning_router",
]
