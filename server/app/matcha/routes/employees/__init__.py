"""Employees router package.

Split from a 5,425-line flat `employees.py` on 2026-05-16. Submodules
are appended into `_legacy.router` via `include_router` until Phase 7
completes the extraction. External import path
`app.matcha.routes.employees` stable.
"""
from ._legacy import (
    router,
    EmployeeCreateRequest,
)
from ._shared import _refresh_risk_assessment
from .pto_admin import router as pto_admin_router
from .leave_admin import router as leave_admin_router

# Submodules included into main router. Order matches original source so
# 1-segment static routes (e.g. /oig-summary) remain shadowed by crud's
# /{employee_id} catch-all — preserves status quo.
from .leave import router as _leave_router; router.include_router(_leave_router)
from .incidents import router as _incidents_router; router.include_router(_incidents_router)
from .oig import router as _oig_router; router.include_router(_oig_router)

__all__ = [
    "router",
    "pto_admin_router",
    "leave_admin_router",
    "_refresh_risk_assessment",
    "EmployeeCreateRequest",
]
