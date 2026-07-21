"""Provisioning router package (J7 split of the 2388-line provisioning.py).

One APIRouter aggregating the per-domain sub-routers. `router` is re-exported
unchanged, so integrations/__init__.py `from .provisioning import router` works.
All routes carry full paths (/google-workspace, /slack, /runs, /hris) so mount
order is cosmetic — no shadowing.
"""
from fastapi import APIRouter

from .google import router as _google_router
from .slack import router as _slack_router
from .runs import router as _runs_router
from .hris import router as _hris_router

router = APIRouter()
for _r in (_google_router, _slack_router, _runs_router, _hris_router):
    router.include_router(_r)

__all__ = ["router"]
