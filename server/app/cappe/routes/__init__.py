"""Cappe router aggregator.

Mounted standalone at /api/cappe in main.py — NOT under matcha_router, so it
never passes through matcha's require_feature chain (Cappe has no company /
feature flags). Auth is per-endpoint via require_cappe_account; the auth,
templates, and public sub-routers are intentionally unauthenticated.
"""
from fastapi import APIRouter

from .auth import router as auth_router
from .pages import router as pages_router
from .public import router as public_router
from .sites import router as sites_router
from .templates import router as templates_router

cappe_router = APIRouter(tags=["cappe"])

cappe_router.include_router(auth_router)
cappe_router.include_router(templates_router)
cappe_router.include_router(public_router)
cappe_router.include_router(sites_router)
cappe_router.include_router(pages_router)

__all__ = ["cappe_router"]
