"""Employee-schedule router package (feature `employee_schedule`).

Shift scheduling over the existing roster: shift CRUD + publish + weekly view
(shifts.py, owns the aggregate paths), employee assignment (assignments.py),
reusable templates + recurrence generation (templates.py), and admin review of
employee swap/unavailability requests (requests.py). Mounted at
`/employee-schedule` in routes/__init__.py behind require_feature.
"""

from fastapi import APIRouter

from .shifts import router as _shifts_router
from .assignments import router as _assignments_router
from .templates import router as _templates_router
from .requests import router as _requests_router

router = APIRouter()
router.include_router(_shifts_router)
router.include_router(_assignments_router)
router.include_router(_templates_router)
router.include_router(_requests_router)

__all__ = ["router"]
