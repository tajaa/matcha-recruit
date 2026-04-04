"""Core routes aggregation."""

from fastapi import APIRouter, Depends

from .auth import router as auth_router
from .admin import router as admin_router
from .blog import router as blog_router
from .policies import router as policies_router
from .handbooks import router as handbooks_router
from .public_signatures import router as public_signatures_router
from .compliance import router as compliance_router
from .bulk_import import router as bulk_import_router
from .chat import router as chat_router, ws_router as chat_ws_router
from .contact import router as contact_router
from .leads_agent import router as leads_agent_router
from .posters import router as posters_router
from .hr_news import router as hr_news_router
from .admin_handbook_references import router as admin_handbook_references_router
from .legislative_tracker import router as legislative_tracker_router
from .investigation_invite import router as investigation_invite_router
from .candidate_invite import router as candidate_invite_router
from .sso import router as sso_router
from .credential_templates import router as credential_templates_router
from .inbox import router as inbox_router
from .channels import router as channels_router
from .channels_ws import router as channels_ws_router
from ...matcha.dependencies import require_feature

# Create main core router
core_router = APIRouter()

# Mount sub-routers
core_router.include_router(auth_router, prefix="/auth", tags=["auth"])
core_router.include_router(admin_router, prefix="/admin", tags=["admin"])
core_router.include_router(admin_handbook_references_router, tags=["admin-handbooks"])
core_router.include_router(blog_router, prefix="/blogs", tags=["blog"])
core_router.include_router(policies_router, tags=["policies"],
                           dependencies=[Depends(require_feature("policies"))])
core_router.include_router(handbooks_router, tags=["handbooks"],
                           dependencies=[Depends(require_feature("handbooks"))])
core_router.include_router(public_signatures_router, tags=["public-signatures"])
core_router.include_router(compliance_router, prefix="/compliance", tags=["compliance"],
                           dependencies=[Depends(require_feature("compliance"))])
core_router.include_router(bulk_import_router, prefix="/bulk", tags=["bulk-import"])
core_router.include_router(chat_router, prefix="/chat", tags=["chat"])
core_router.include_router(contact_router, prefix="/contact", tags=["contact"])
core_router.include_router(leads_agent_router, prefix="/leads-agent", tags=["leads-agent"])
core_router.include_router(posters_router, prefix="/compliance/posters", tags=["compliance-posters"],
                           dependencies=[Depends(require_feature("compliance"))])
core_router.include_router(hr_news_router, prefix="/admin/news", tags=["hr-news"])
core_router.include_router(legislative_tracker_router, prefix="/admin/legislative-tracker", tags=["legislative-tracker"])
core_router.include_router(investigation_invite_router, tags=["investigation-invite"])
core_router.include_router(candidate_invite_router, tags=["candidate-invite"])
core_router.include_router(sso_router, prefix="/sso", tags=["sso"])
core_router.include_router(credential_templates_router, prefix="/credential-templates",
                           tags=["credential-templates"],
                           dependencies=[Depends(require_feature("credential_templates"))])
core_router.include_router(inbox_router, prefix="/inbox", tags=["inbox"])
core_router.include_router(channels_router, prefix="/channels", tags=["channels"])

# Export individual routers for backwards compatibility
__all__ = [
    "core_router",
    "auth_router",
    "admin_router",
    "blog_router",
    "policies_router",
    "handbooks_router",
    "public_signatures_router",
    "compliance_router",
    "bulk_import_router",
    "chat_router",
    "chat_ws_router",
    "contact_router",
    "leads_agent_router",
    "posters_router",
    "hr_news_router",
    "legislative_tracker_router",
    "sso_router",
    "credential_templates_router",
    "inbox_router",
    "channels_router",
    "channels_ws_router",
]
