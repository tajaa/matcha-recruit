"""Employees router package.

Split from a 5,425-line flat `employees.py` on 2026-05-16. CRUD lives in
`crud.py` and owns the package's main router (it declares the empty-path
collection routes `@router.post("")` / `@router.get("")`). Other domain
submodules append into the same router via `include_router(...)` below.

Two sibling routers — `pto_admin_router`, `leave_admin_router` — are
mounted at separate prefixes in `routes/__init__.py` and are NOT
included into the main router.

External import path `app.matcha.routes.employees` stable.
"""
from .crud import router, EmployeeCreateRequest
from ._shared import _refresh_risk_assessment
from .pto_admin import router as pto_admin_router
from .leave_admin import router as leave_admin_router

# Submodules included into the main router. crud's /{employee_id} catch-all
# registers FIRST (above), so 1-segment static routes in these submodules
# (e.g. /oig-summary, /incident-counts, /onboarding-draft) remain shadowed
# as they were in the original flat file — preserves status quo.
from .onboarding import router as _onboarding_router; router.include_router(_onboarding_router)
from .offboarding import router as _offboarding_router; router.include_router(_offboarding_router)
from .invitations import router as _invitations_router; router.include_router(_invitations_router)
from .bulk_upload import router as _bulk_upload_router; router.include_router(_bulk_upload_router)
from .leave import router as _leave_router; router.include_router(_leave_router)
from .incidents import router as _incidents_router; router.include_router(_incidents_router)
from .credentials import router as _credentials_router; router.include_router(_credentials_router)
from .oig import router as _oig_router; router.include_router(_oig_router)

__all__ = [
    "router",
    "pto_admin_router",
    "leave_admin_router",
    "_refresh_risk_assessment",
    "EmployeeCreateRequest",
]
