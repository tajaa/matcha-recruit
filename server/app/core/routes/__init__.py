"""Core routes aggregation."""

from fastapi import APIRouter

from .auth import router as auth_router
from .blog import router as blog_router
from .policies import router as policies_router
from .public_signatures import router as public_signatures_router
from .compliance import router as compliance_router
from .bulk_import import router as bulk_import_router
from .chat import router as chat_router, ws_router as chat_ws_router
from .contact import router as contact_router
from .projects import router as projects_router
from .outreach import router as outreach_router
from .leads_agent import router as leads_agent_router

# Create main core router
core_router = APIRouter()

# Mount sub-routers
core_router.include_router(auth_router, prefix="/auth", tags=["auth"])
core_router.include_router(blog_router, prefix="/blogs", tags=["blog"])
core_router.include_router(policies_router, tags=["policies"])
core_router.include_router(public_signatures_router, tags=["public-signatures"])
core_router.include_router(compliance_router, prefix="/compliance", tags=["compliance"])
core_router.include_router(bulk_import_router, prefix="/bulk", tags=["bulk-import"])
core_router.include_router(chat_router, prefix="/chat", tags=["chat"])
core_router.include_router(contact_router, prefix="/contact", tags=["contact"])
core_router.include_router(projects_router, prefix="/projects", tags=["projects"])
core_router.include_router(outreach_router, tags=["outreach"])
core_router.include_router(leads_agent_router, prefix="/leads-agent", tags=["leads-agent"])

# Export individual routers for backwards compatibility
__all__ = [
    "core_router",
    "auth_router",
    "blog_router",
    "policies_router",
    "public_signatures_router",
    "compliance_router",
    "bulk_import_router",
    "chat_router",
    "chat_ws_router",
    "contact_router",
    "projects_router",
    "outreach_router",
    "leads_agent_router",
]
