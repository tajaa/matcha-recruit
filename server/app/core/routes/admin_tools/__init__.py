"""admin_tools grouping folder — admin-facing operational surfaces."""
from app.core.routes.admin_tools.admin_onboarding import router as admin_onboarding_router
from app.core.routes.admin_tools.admin_compliance_pilot import router as compliance_pilot_router
from app.core.routes.admin_tools.scope_registry import router as scope_registry_router
from app.core.routes.admin_tools.legislative_tracker import router as legislative_tracker_router
from app.core.routes.admin_tools.ai_usage_admin import router as ai_usage_admin_router
from app.core.routes.admin_tools.bulk_import import router as bulk_import_router
from app.core.routes.admin_tools.leads_agent import router as leads_agent_router

__all__ = [
    "admin_onboarding_router",
    "compliance_pilot_router",
    "scope_registry_router",
    "legislative_tracker_router",
    "ai_usage_admin_router",
    "bulk_import_router",
    "leads_agent_router",
]
