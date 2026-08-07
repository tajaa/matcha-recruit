"""Tell-Us internal admin package. Every sub-router carries a router-level
Depends(require_tellus_admin); mutating endpoints ALSO take the dep as a
parameter to identify the actor for tellus_admin_audit (FastAPI caches the
dependency resolution — one DB lookup per request either way)."""
from fastapi import APIRouter

from .accounts import router as accounts_router
from .audit import router as audit_router
from .brands import router as brands_router
from .claims import router as claims_router
from .economy import router as economy_router
from .moderation import router as moderation_router
from .updates import router as updates_router

router = APIRouter()
for _r in (updates_router, accounts_router, brands_router, claims_router,
           moderation_router, economy_router, audit_router):
    router.include_router(_r)

__all__ = ["router"]
