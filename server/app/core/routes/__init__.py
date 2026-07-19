"""Core routes aggregation."""

from fastapi import APIRouter, Depends

from .auth import router as auth_router
from .admin import router as admin_router
from .admin_onboarding import router as admin_onboarding_router
from .admin_compliance_pilot import router as compliance_pilot_router
from .blog import router as blog_router
from .policies import router as policies_router
from .handbooks import router as handbooks_router
from .handbooks import public_router as handbooks_public_router
from .public_signatures import router as public_signatures_router
from .compliance import (
    router as compliance_router,
    lite_router as compliance_lite_router,
    shared_router as compliance_shared_router,
)
from .bulk_import import router as bulk_import_router
from .chat import router as chat_router, ws_router as chat_ws_router
from .contact import router as contact_router
from .leads_agent import router as leads_agent_router
from .posters import router as posters_router
from .hr_news import router as hr_news_router, public_router as hr_news_public_router
from .admin_handbook_references import router as admin_handbook_references_router
from .legislative_tracker import router as legislative_tracker_router
from .scope_registry import router as scope_registry_router
from .investigation_invite import router as investigation_invite_router
from .candidate_invite import router as candidate_invite_router
from .sso import router as sso_router
from .credential_templates import router as credential_templates_router
from .push import router as push_router
from .profile_resume import router as profile_resume_router
from .newsletter import public_router as newsletter_public_router, admin_router as newsletter_admin_router
from .client_errors import router as client_errors_router
from .server_errors import router as server_errors_router
from .traffic import router as traffic_router
from .usage import router as usage_router
from .landing_media import public_router as landing_media_public_router, admin_router as landing_media_admin_router
from .resources import router as resources_router
from .matcha_lite_pricing_admin import router as matcha_lite_pricing_admin_router
from .handbook_gap_analyzer import router as handbook_gap_analyzer_router
from .expert_advice import router as expert_advice_router
from ...matcha.dependencies import require_feature, require_any_feature
from ..feature_flags import COMPLIANCE_READ_FEATURES, COMPLIANCE_SHARED_FEATURES

# Create main core router
core_router = APIRouter()

# Mount sub-routers
core_router.include_router(auth_router, prefix="/auth", tags=["auth"])
core_router.include_router(admin_router, prefix="/admin", tags=["admin"])
core_router.include_router(admin_onboarding_router, prefix="/admin", tags=["admin-onboarding"])
core_router.include_router(compliance_pilot_router, prefix="/admin/pilot", tags=["compliance-pilot"])
core_router.include_router(admin_handbook_references_router, tags=["admin-handbooks"])
core_router.include_router(blog_router, prefix="/blogs", tags=["blog"])
core_router.include_router(policies_router, tags=["policies"],
                           dependencies=[Depends(require_feature("policies"))])
core_router.include_router(handbooks_router, tags=["handbooks"],
                           dependencies=[Depends(require_feature("handbooks"))])
# Public read-only handbook share links — no auth, no feature gate (the token is
# validated internally, and require_feature needs a logged-in user to gate on).
core_router.include_router(handbooks_public_router, prefix="/shared/handbook",
                           tags=["handbooks-public"])
core_router.include_router(public_signatures_router, tags=["public-signatures"])
# Lite-friendly subset (calendar, locations-read, alert read/dismiss) is mounted
# with a broad gate — any of compliance / compliance_lite / incidents (matcha-lite's
# paid flag) — so matcha-lite tenants can use the Compliance Calendar even though
# the full Compliance feature is off. All mutating location endpoints (create/
# update/delete/facility-attributes PATCH) live on the full-compliance-gated
# `router` below, not here.
core_router.include_router(
    compliance_lite_router,
    prefix="/compliance",
    tags=["compliance-lite"],
    dependencies=[Depends(require_any_feature(*COMPLIANCE_READ_FEATURES))],
)
# Read-only viewers (requirements, jurisdiction-stack, summary, upcoming-legislation,
# categories) — admit full `compliance` (Pro) OR `compliance_lite` (Matcha-X taste).
core_router.include_router(compliance_shared_router, prefix="/compliance", tags=["compliance-shared"],
                           dependencies=[Depends(require_any_feature(*COMPLIANCE_SHARED_FEATURES))])
core_router.include_router(compliance_router, prefix="/compliance", tags=["compliance"],
                           dependencies=[Depends(require_feature("compliance"))])
core_router.include_router(bulk_import_router, prefix="/bulk", tags=["bulk-import"])
core_router.include_router(chat_router, prefix="/chat", tags=["chat"])
core_router.include_router(contact_router, prefix="/contact", tags=["contact"])
core_router.include_router(leads_agent_router, prefix="/leads-agent", tags=["leads-agent"])
core_router.include_router(posters_router, prefix="/compliance/posters", tags=["compliance-posters"],
                           dependencies=[Depends(require_feature("compliance"))])
core_router.include_router(hr_news_router, prefix="/admin/news", tags=["hr-news"])
core_router.include_router(hr_news_public_router, prefix="/news", tags=["hr-news-public"])
core_router.include_router(legislative_tracker_router, prefix="/admin/legislative-tracker", tags=["legislative-tracker"])
core_router.include_router(scope_registry_router, prefix="/admin/scope-registry", tags=["scope-registry"])
core_router.include_router(investigation_invite_router, tags=["investigation-invite"])
core_router.include_router(candidate_invite_router, tags=["candidate-invite"])
core_router.include_router(sso_router, prefix="/sso", tags=["sso"])
core_router.include_router(credential_templates_router, prefix="/credential-templates",
                           tags=["credential-templates"],
                           dependencies=[Depends(require_feature("credential_templates"))])
core_router.include_router(push_router, prefix="/push", tags=["push"])
core_router.include_router(profile_resume_router, prefix="/users", tags=["profile-resume"])
core_router.include_router(newsletter_public_router, prefix="/newsletter", tags=["newsletter-public"])
core_router.include_router(newsletter_admin_router, prefix="/admin/newsletter", tags=["newsletter-admin"])
core_router.include_router(resources_router, prefix="/resources", tags=["resources"])
core_router.include_router(matcha_lite_pricing_admin_router, prefix="/admin", tags=["matcha-lite-pricing-admin"])
core_router.include_router(
    handbook_gap_analyzer_router,
    prefix="/resources/handbook-gap-analyzer",
    tags=["handbook-gap-analyzer"],
)
core_router.include_router(expert_advice_router, prefix="/expert-advice", tags=["expert-advice"])
core_router.include_router(landing_media_public_router, tags=["landing-media-public"])
core_router.include_router(landing_media_admin_router, prefix="/admin", tags=["landing-media-admin"])
core_router.include_router(client_errors_router, tags=["client-errors"])
core_router.include_router(server_errors_router, tags=["server-errors"])
core_router.include_router(traffic_router, tags=["traffic"])
core_router.include_router(usage_router, tags=["usage"])

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
    "scope_registry_router",
    "sso_router",
    "credential_templates_router",
    "push_router",
    "profile_resume_router",
]
