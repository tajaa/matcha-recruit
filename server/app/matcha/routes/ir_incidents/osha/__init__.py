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

The mount and its two stacked gates are unchanged and still live in
`ir_incidents/__init__.py` — `incidents` from the package mount, plus
`osha_logs` on the include.
"""
from fastapi import APIRouter

from .ita import router as _ita_router
from .logs import router as _logs_router
from .recordability import router as _recordability_router
from .summary_300a import router as _summary_300a_router

router = APIRouter()
router.include_router(_logs_router)
router.include_router(_summary_300a_router)
router.include_router(_ita_router)
router.include_router(_recordability_router)

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
