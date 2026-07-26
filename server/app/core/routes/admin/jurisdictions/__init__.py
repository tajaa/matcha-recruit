"""Admin jurisdictions router package (split of the 4,558-line jurisdictions.py).

Include order is load-bearing: it reproduces the monolith's original route
registration order exactly (each submodule's line range was cut at a
``@router.`` decorator boundary, in original file order). Hard constraint:
``checks.py``'s ``POST /jurisdictions/top-metros/check`` must register before
``POST /jurisdictions/{jurisdiction_id}/check`` — the latter path has no
``:uuid`` converter, so it would otherwise swallow the former. That ordering
is preserved because both routes live inside checks.py in their original
relative order.

Redis cache-key note: writers and invalidators of the same admin cache keys
(``admin_jurisdictions_list_key``, ``admin_jurisdiction_detail_key``,
``admin_jurisdiction_policy_overview_key``, the ``admin:quality-audit:v2:``
pattern) are split across files (e.g. cleanup.py/requirements.py invalidate
keys that crud_listing.py/overviews.py write). This is a pre-existing
semantic coupling via ``app.core.services.redis_cache``, not a code
dependency — no code moved to preserve it.
"""
from fastapi import APIRouter

from app.core.routes.admin.jurisdictions.crud_listing import router as _crud_listing
from app.core.routes.admin.jurisdictions.cleanup import router as _cleanup
from app.core.routes.admin.jurisdictions.overviews import router as _overviews
from app.core.routes.admin.jurisdictions.quality import router as _quality
from app.core.routes.admin.jurisdictions.staleness import router as _staleness
from app.core.routes.admin.jurisdictions.detail_evals import router as _detail_evals
from app.core.routes.admin.jurisdictions.requirements import router as _requirements
from app.core.routes.admin.jurisdictions.checks import router as _checks
from app.core.routes.admin.jurisdictions.requests_coverage import router as _requests_coverage

router = APIRouter()
for _r in (
    _crud_listing,
    _cleanup,
    _overviews,
    _quality,
    _staleness,
    _detail_evals,
    _requirements,
    _checks,
    _requests_coverage,
):
    router.include_router(_r)

__all__ = ["router"]
