"""Employee-schedule router package (feature `employee_schedule`).

Shift scheduling over the existing roster: shift CRUD + publish + weekly view
(shifts.py, owns the aggregate paths), employee assignment (assignments.py),
week templates + recurrence generation (week_templates.py), and admin review
of employee swap/unavailability requests (requests.py). Mounted at
`/employee-schedule` in routes/__init__.py behind require_feature.
"""

from fastapi import APIRouter

from .shifts import router as _shifts_router
from .assignments import router as _assignments_router
from .week_templates import router as _week_templates_router
from .requests import router as _requests_router
from .availability import router as _availability_router
from .jobs import router as _jobs_router
from .attestations import router as _attestations_router
from .eligibility import router as _eligibility_router
from .assistant import router as _assistant_router
from .auto_schedules import router as _auto_schedules_router
from .audit_logs import router as _audit_logs_router

router = APIRouter()
router.include_router(_shifts_router)
router.include_router(_assignments_router)
router.include_router(_week_templates_router)
router.include_router(_requests_router)
router.include_router(_availability_router)
router.include_router(_jobs_router)
router.include_router(_attestations_router)
router.include_router(_eligibility_router)
router.include_router(_assistant_router)
router.include_router(_auto_schedules_router)
router.include_router(_audit_logs_router)

# Sibling router — own prefix (/schedule-intelligence) + its own single-flag
# gate (schedule_intelligence, not employee_schedule), mounted separately in
# routes/__init__.py rather than folded into this package's aggregator.
from .intelligence import router as schedule_intelligence_router  # noqa: F401,E402

__all__ = ["router", "schedule_intelligence_router"]
