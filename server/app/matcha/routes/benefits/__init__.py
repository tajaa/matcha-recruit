"""Benefits router package. Split from a flat benefits.py on 2026-07-23 to
add the open-enrollment workflow (plans/tiers, OE periods, elections,
life events) alongside the original eligibility/risk tool.

router -> /benefits (feature-gated at the mount in routes/__init__.py, not here)

No submodule declares empty-path routes, so `router` is a fresh aggregator
(the matcha_work/ variant), not the crud-owns-router pattern used by
ir_incidents/employees.
"""
from fastapi import APIRouter

router = APIRouter()

from .eligibility import router as _eligibility_router

router.include_router(_eligibility_router)

from .plans import router as _plans_router

router.include_router(_plans_router)

from .enrollment import router as _enrollment_router

router.include_router(_enrollment_router)
