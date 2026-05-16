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

__all__ = [
    "router",
    "pto_admin_router",
    "leave_admin_router",
    "_refresh_risk_assessment",
    "EmployeeCreateRequest",
]
