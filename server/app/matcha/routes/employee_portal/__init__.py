"""Employee Self-Service Portal router package.

Split from a 1,727-line flat employee_portal.py (33 routes; URL surface
unchanged). No submodule declares an empty-path route, so the package router
is a fresh aggregator (matcha_work variant — see routes/CLAUDE.md).
Prefix /v1/portal is applied at the parent mount in routes/__init__.py.
"""
from fastapi import APIRouter

# Back-compat attribute surface (tests reference employee_portal_routes.require_employee_record)
from app.matcha.dependencies import (  # noqa: F401
    require_employee, require_employee_record, require_feature,
)
from ._shared import (  # noqa: F401
    _pto_dep, _policies_dep, _compliance_plus_dep, _schedule_dep, _benefits_dep,
)

router = APIRouter()

# Include order mirrors original file order (keeps OpenAPI ordering identical).
from .profile import router as _profile_router
router.include_router(_profile_router)
from .pto import router as _pto_router
router.include_router(_pto_router)
from .leave import router as _leave_router
router.include_router(_leave_router)
from .schedule import router as _schedule_router
router.include_router(_schedule_router)
from .documents import router as _documents_router
router.include_router(_documents_router)
from .policies import router as _policies_router
router.include_router(_policies_router)
from .onboarding import router as _onboarding_router
router.include_router(_onboarding_router)
from .priorities import router as _priorities_router
router.include_router(_priorities_router)
from .credential_documents import router as _credential_documents_router
router.include_router(_credential_documents_router)
from .benefits import router as _benefits_router
router.include_router(_benefits_router)
