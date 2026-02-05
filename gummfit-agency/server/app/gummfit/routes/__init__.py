"""Gummfit (Creator Agency) routes aggregation."""

from fastapi import APIRouter

from .creators import router as creators_router
from .agencies import router as agencies_router
from .deals import router as deals_router
from .campaigns import router as campaigns_router
from .gumfit import router as gumfit_admin_router
from .assets import router as assets_router

# Create main Gummfit router
gummfit_router = APIRouter()

# Alias for backward compatibility (single 'm' spelling)
gumfit_router = gummfit_router

# Mount sub-routers
gummfit_router.include_router(creators_router, prefix="/creators", tags=["creators"])
gummfit_router.include_router(agencies_router, prefix="/agencies", tags=["agencies"])
gummfit_router.include_router(deals_router, prefix="/deals", tags=["deals"])
gummfit_router.include_router(campaigns_router, prefix="/campaigns", tags=["campaigns"])
gummfit_router.include_router(gumfit_admin_router, prefix="/gumfit", tags=["gumfit-admin"])
gummfit_router.include_router(assets_router, prefix="/gumfit/assets", tags=["gumfit-assets"])

# Export individual routers for backwards compatibility
__all__ = [
    "gummfit_router",
    "gumfit_router",  # Alias with single 'm' for backward compatibility
    "creators_router",
    "agencies_router",
    "deals_router",
    "campaigns_router",
    "gumfit_admin_router",
    "assets_router",
]
