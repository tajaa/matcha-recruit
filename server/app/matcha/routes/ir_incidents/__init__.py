"""IR Incidents router package — composed from per-domain submodules.

External callers continue to do:

    from app.matcha.routes.ir_incidents import router as ir_incidents_router

Symbols imported by other routers (`broker_portfolio.py`, `inbound_email.py`)
are re-exported here so those callers never need to know whether a helper
currently lives in `_legacy.py` or its eventual submodule home. As helpers
migrate out of `_legacy.py`, flip the corresponding `from ._legacy import`
line below to point at the new module.

Prefix and feature-gate are applied at the parent mount in
`server/app/matcha/routes/__init__.py` — this router stays bare.
"""
# The package's exported `router` IS `_legacy.router`. New submodules will
# be added via `router.include_router(...)` below as they arrive. Wrapping
# `_legacy.router` inside a bare `APIRouter()` would break because `_legacy`
# has routes registered with `path=""` (e.g. `@router.post("")`) — FastAPI
# refuses to compose two empty path segments.
from ._legacy import router  # noqa: F401  (package public symbol)

# Submodules — each `include_router` injects its routes into the package router.
# Order matters: routers with static path prefixes (e.g. /anonymous-reporting,
# /osha, /analytics) must be registered BEFORE any router that owns the
# catch-all `/{incident_id}` path. _legacy.router currently owns the catch-all,
# so static-prefix submodules go here ABOVE `from ._legacy import router`.
# Audit-log path is `/{incident_id}/audit-log` (specific suffix) — safe.
from .anonymous_reporting import router as _anonymous_reporting_router
router.include_router(_anonymous_reporting_router)

from .documents import router as _documents_router
router.include_router(_documents_router)

from .osha import router as _osha_router
router.include_router(_osha_router)

from .investigation_interviews import router as _investigation_interviews_router
router.include_router(_investigation_interviews_router)

from .ai_analysis import router as _ai_analysis_router
router.include_router(_ai_analysis_router)

from .analytics import router as _analytics_router
router.include_router(_analytics_router)

from .copilot import router as _copilot_router
router.include_router(_copilot_router)

from .audit_log import router as _audit_log_router
router.include_router(_audit_log_router)

# External re-exports. Keep `# noqa: F401` — these are package-level
# re-exports, not local usages.
from .analytics import compute_wc_metrics  # noqa: F401  (used by broker_portfolio.py)
from ._legacy import (  # noqa: F401  (used by inbound_email.py)
    _parse_occurred_at,
    generate_incident_number,
    send_ir_notifications_task,
)
from .copilot import _close_incident_via_copilot  # noqa: F401  (future cross-router use)
