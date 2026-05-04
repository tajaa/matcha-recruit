"""Core routes aggregation."""

from fastapi import APIRouter, Depends

from .auth import router as auth_router
from .admin import router as admin_router
from .blog import router as blog_router
from .policies import router as policies_router
from .handbooks import router as handbooks_router
from .public_signatures import router as public_signatures_router
from .compliance import router as compliance_router, lite_router as compliance_lite_router
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
from .channel_job_postings import router as channel_job_postings_router
from .profile_resume import router as profile_resume_router
from .newsletter import public_router as newsletter_public_router, admin_router as newsletter_admin_router
from .client_errors import router as client_errors_router
from .server_errors import router as server_errors_router
from .landing_media import public_router as landing_media_public_router, admin_router as landing_media_admin_router
from .resources import router as resources_router
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
# Lite-friendly subset (calendar, locations-read, alert read/dismiss) is mounted
# first WITHOUT the compliance feature gate so matcha-lite tenants can use the
# Compliance Calendar even though the full Compliance feature is off.
core_router.include_router(compliance_lite_router, prefix="/compliance", tags=["compliance-lite"])
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
core_router.include_router(channel_job_postings_router, prefix="/channels", tags=["channel-job-postings"])
core_router.include_router(profile_resume_router, prefix="/users", tags=["profile-resume"])
core_router.include_router(newsletter_public_router, prefix="/newsletter", tags=["newsletter-public"])
core_router.include_router(newsletter_admin_router, prefix="/admin/newsletter", tags=["newsletter-admin"])
core_router.include_router(resources_router, prefix="/resources", tags=["resources"])
core_router.include_router(landing_media_public_router, tags=["landing-media-public"])
core_router.include_router(landing_media_admin_router, prefix="/admin", tags=["landing-media-admin"])
core_router.include_router(client_errors_router, tags=["client-errors"])
core_router.include_router(server_errors_router, tags=["server-errors"])

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
    "channel_job_postings_router",
    "profile_resume_router",
]
