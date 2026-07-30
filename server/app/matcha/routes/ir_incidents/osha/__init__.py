"""OSHA log + form endpoints for IR Incidents.

Split out of the 1,627-line flat `osha.py` (refactor round 2, stage 5) into
four groups that share no state beyond `_shared.py`:

| Module | Concern | Routes |
|---|---|---|
| `logs.py` | 300 log + CSV, privacy-case list, per-incident 301 form | 4 |
| `summary_300a.py` | 300A computed summary, admin save, PDF + CSV export | 4 |
| `ita.py` | ITA validate, bulk CSV, credentials, direct submit, history | 6 |
| `recordability.py` | Manual classification update + Gemini determination | 2 |
| `_shared.py` | Attestation gate, 300A aggregation, headcount, JSON coercion | — |
| `_pdf.py` | WeasyPrint Form 300A template (was `_osha_pdf.py`) | — |

Fresh-aggregator variant (see `routes/CLAUDE.md`): no submodule declares an
empty-path route, so `router` here is a bare `APIRouter()` the four sub-routers
include into, rather than one submodule's router owning the others.

The parent mount (`ir_incidents/__init__.py`) still applies `incidents`; this
package's own include now carries a 3-way OSHA sub-split (2026-07-30, for
/admin/products composability) instead of one `osha_logs` gate:

- `osha_logs` OR `osha_export` — logs.py, summary_300a.py, recordability.py
  (CSV export + manual recordability work with either flag; interactive-only
  endpoints add their own per-route `osha_logs` gate — see each module).
- `osha_auto_report` — ita.py (electronic ITA submission).
"""
from fastapi import APIRouter, Depends

from app.matcha.dependencies import require_any_feature, require_feature

from .ita import router as _ita_router
from .logs import router as _logs_router
from .recordability import router as _recordability_router
from .summary_300a import router as _summary_300a_router

router = APIRouter()
_export_or_full = [Depends(require_any_feature("osha_logs", "osha_export"))]
router.include_router(_logs_router, dependencies=_export_or_full)
router.include_router(_summary_300a_router, dependencies=_export_or_full)
router.include_router(_ita_router, dependencies=[Depends(require_feature("osha_auto_report"))])
router.include_router(_recordability_router, dependencies=_export_or_full)

# Re-exported for tests + any future cross-router consumer. `_missing_ita_fields`
# and the privacy/masking helpers were importable from the flat `osha` module;
# keep that surface stable so `from ...ir_incidents.osha import X` still works.
from ._shared import EXPORT_DISCLAIMER, _attest_export  # noqa: E402,F401
from .ita import _missing_ita_fields  # noqa: E402,F401
from .logs import (  # noqa: E402,F401
    _injured_persons,
    _mask_from_reason,
    _osha_case_views,
    _resolve_osha_description,
)

__all__ = ["router"]
