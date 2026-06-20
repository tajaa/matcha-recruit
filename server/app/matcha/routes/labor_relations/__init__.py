"""Labor Relations router package — union / CBA administration.

Phase 1 surface: CBA document store + AI clause library (`cba.py`) and the
grievance workflow with contractual step-deadlines (`grievances.py`).

The package's exported `router` IS `grievances.router` — it owns the grievance
lifecycle routes; `cba.py`'s routes are composed onto it below. No submodule
uses an empty path (`@router.X("")`), so every route is unambiguous under the
parent mount.

Prefix `/labor` and `require_feature("labor_relations")` are applied at the
parent mount in `server/app/matcha/routes/__init__.py` — this router stays bare.
"""

from .grievances import router  # noqa: F401  (package public symbol)

from .cba import router as _cba_router
router.include_router(_cba_router)
