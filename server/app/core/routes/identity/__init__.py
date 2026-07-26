"""identity grouping folder — auth-adjacent surfaces (SSO, invites, profile, push)."""
from app.core.routes.identity.sso import router as sso_router
from app.core.routes.identity.profile_resume import router as profile_resume_router
from app.core.routes.identity.push import router as push_router
from app.core.routes.identity.candidate_invite import router as candidate_invite_router
from app.core.routes.identity.investigation_invite import router as investigation_invite_router

__all__ = [
    "sso_router",
    "profile_resume_router",
    "push_router",
    "candidate_invite_router",
    "investigation_invite_router",
]
