"""Cappe router aggregator.

Mounted standalone at /api/cappe in main.py — NOT under matcha_router, so it
never passes through matcha's require_feature chain (Cappe has no company /
feature flags). Auth is per-endpoint via require_cappe_account; the auth,
templates, and public sub-routers are intentionally unauthenticated.
"""
from fastapi import APIRouter

from .auth import router as auth_router
from .blog import router as blog_router
from .bookings import router as bookings_router
from .forms import router as forms_router
from .newsletter import router as newsletter_router
from .pages import router as pages_router
from .public import router as public_router
from .rider import router as rider_router
from .shop import router as shop_router
from .sites import router as sites_router
from .templates import router as templates_router
from .uploads import router as uploads_router

cappe_router = APIRouter(tags=["cappe"])

# Unauthenticated surfaces.
cappe_router.include_router(auth_router)
cappe_router.include_router(templates_router)
cappe_router.include_router(public_router)

# Authenticated, per-site (each route gates on require_cappe_account + get_owned_site).
cappe_router.include_router(sites_router)
cappe_router.include_router(pages_router)
cappe_router.include_router(shop_router)
cappe_router.include_router(newsletter_router)
cappe_router.include_router(forms_router)
cappe_router.include_router(bookings_router)
cappe_router.include_router(rider_router)
cappe_router.include_router(blog_router)
cappe_router.include_router(uploads_router)

__all__ = ["cappe_router"]
