"""Dashboard router package — split from flat dashboard.py (14 routes, URL
surface unchanged). Fresh-aggregator variant: no submodule declares an
empty-path route. Prefix /dashboard applied at the parent mount.
"""
from fastapi import APIRouter

router = APIRouter()

from .stats import router as _stats_router
router.include_router(_stats_router)
from .risk_flags import router as _risk_flags_router
router.include_router(_risk_flags_router)
from .notifications import router as _notifications_router
router.include_router(_notifications_router)
from .credentials import router as _credentials_router
router.include_router(_credentials_router)
from .upcoming import router as _upcoming_router
router.include_router(_upcoming_router)
from .escalated_queries import router as _escalated_queries_router
router.include_router(_escalated_queries_router)
from .sidebar_badges import router as _sidebar_badges_router
router.include_router(_sidebar_badges_router)

# External re-exports — routes/matcha_work/workspace.py:468 lazily does
#   from app.matcha.routes.dashboard import _UPCOMING_SOURCES, _apply_company_filter,
#       _severity_from_days, UpcomingItem
from .upcoming import _UPCOMING_SOURCES, _apply_company_filter, _severity_from_days  # noqa: F401
from app.matcha.models.dashboard import UpcomingItem  # noqa: F401
