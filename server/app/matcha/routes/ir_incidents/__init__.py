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
from fastapi import Depends

from app.matcha.dependencies import require_feature

# The package's exported `router` IS `crud.router`. CRUD owns the
# empty-path collection routes (`@router.post("")`, `@router.get("")`).
# Wrapping crud.router inside a fresh `APIRouter()` and including it
# would error: FastAPI refuses to compose two empty-prefix routers with
# empty-path children. By exposing crud.router directly, the only prefix
# in play is the one applied at the parent mount in
# `server/app/matcha/routes/__init__.py`. All other submodules append
# their routes via `router.include_router(...)` below.
from .crud import router  # noqa: F401  (package public symbol)

# Submodules — each `include_router` appends its routes onto the package
# router AFTER _legacy's routes have already been registered. That ordering
# is safe because no submodule shares both segment-count AND parameter
# pattern with a _legacy catch-all: _legacy's `/{incident_id}` is 1-segment
# while every submodule route is 2+ segments. If a future submodule adds a
# 1-segment route (e.g. `@router.post("")`), it would be shadowed by
# _legacy's collection-root routes and need to land in step 10 (CRUD
# migration) where _legacy's empty-path routes also move out.
from .anonymous_reporting import router as _anonymous_reporting_router
router.include_router(_anonymous_reporting_router)

from .info_requests import router as _info_requests_router
router.include_router(_info_requests_router)

from .documents import router as _documents_router
router.include_router(_documents_router)

from .osha import router as _osha_router
# Additional gate on top of the inherited `incidents` requirement — the
# no-roster matcha_lite_essentials config has incidents on but osha_logs off
# (no employee roster to log injured persons against).
router.include_router(_osha_router, dependencies=[Depends(require_feature("osha_logs"))])

from .investigation_interviews import router as _investigation_interviews_router
router.include_router(_investigation_interviews_router)

from .people import router as _people_router
router.include_router(_people_router)

from .ai_analysis import router as _ai_analysis_router
router.include_router(_ai_analysis_router)

from .analytics import router as _analytics_router
router.include_router(_analytics_router)

from .copilot import router as _copilot_router
router.include_router(_copilot_router)

from .audit_log import router as _audit_log_router
router.include_router(_audit_log_router)

from .claims_readiness import router as _claims_readiness_router
router.include_router(_claims_readiness_router)

from .voice import router as _voice_router
router.include_router(_voice_router)

# External re-exports. Keep `# noqa: F401` — these are package-level
# re-exports, not local usages.
from .analytics import compute_wc_metrics  # noqa: F401  (used by broker_portfolio.py)
from .analytics import compute_behavioral_friction  # noqa: F401  (used by broker_risk_alerts worker)
from ._shared import (  # noqa: F401  (used by inbound_email.py)
    _location_label,
    _parse_occurred_at,
    _read_audio_or_400,
    _safe_json_loads,
    _info_request_effective_status,
    create_incident_core,
    generate_incident_number,
    send_ir_notifications_task,
    send_ir_info_request_notification_task,
)
from .copilot import _close_incident_via_copilot  # noqa: F401  (future cross-router use)
