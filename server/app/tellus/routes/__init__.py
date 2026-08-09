"""Tell-Us router aggregator.

Mounted standalone at /api/tellus in main.py — NOT under matcha_router, so it
never passes through matcha's require_feature chain (Tell-Us has no company /
feature flags). Auth is per-endpoint via the require_tellus_account family; the
auth + public-intake sub-routers are intentionally unauthenticated.
"""
from fastapi import APIRouter

from .admin import router as admin_router
from .auth import router as auth_router
from .billing import router as billing_router
from .board import router as board_router
from .community import router as community_router
from .dms import router as dms_router
from .feedback import router as feedback_router
from .flyer_ai import router as flyer_ai_router
from .gamification import router as gamification_router
from .grants import router as grants_router
from .likes import router as likes_router
from .links import router as links_router
from .marketplace import router as marketplace_router
from .my_reviews import router as my_reviews_router
from .places import router as places_router
from .promo import router as promo_router
from .promo_public import router as promo_public_router
from .prompts import router as prompts_router
from .public_intake import router as public_intake_router
from .rewards import router as rewards_router

tellus_router = APIRouter(tags=["tellus"])


@tellus_router.get("/health")
async def tellus_health():
    """Liveness probe — confirms the tellus router mounted on the same backend."""
    return {"status": "ok", "app": "tellus"}


# Unauthenticated surfaces.
tellus_router.include_router(auth_router)
tellus_router.include_router(public_intake_router)
tellus_router.include_router(promo_public_router)
tellus_router.include_router(community_router)
tellus_router.include_router(places_router)

# Consumer-authenticated (require_consumer per-route).
tellus_router.include_router(rewards_router)
tellus_router.include_router(marketplace_router)
tellus_router.include_router(gamification_router)
tellus_router.include_router(my_reviews_router)

# Brand-authenticated (require_brand per-route).
tellus_router.include_router(links_router)
tellus_router.include_router(prompts_router)
tellus_router.include_router(feedback_router)
tellus_router.include_router(grants_router)
tellus_router.include_router(billing_router)
tellus_router.include_router(flyer_ai_router)

# Mixed-role (per-endpoint dependency — brand opens, either side replies).
tellus_router.include_router(dms_router)
tellus_router.include_router(board_router)
tellus_router.include_router(likes_router)
# Mixed-role: brand campaign/scanner CRUD (require_paid_brand) + consumer
# card reads (require_consumer), per-endpoint.
tellus_router.include_router(promo_router)

# Internal admin (require_tellus_admin per-route — TELLUS_ADMIN_EMAILS allowlist).
tellus_router.include_router(admin_router)

__all__ = ["tellus_router"]
