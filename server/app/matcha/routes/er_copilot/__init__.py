"""ER Copilot routes package.

Split from a 4,132-line flat er_copilot.py into per-concern submodules
(see CLAUDE.md). The URL surface is unchanged and the external import path
``app.matcha.routes.er_copilot`` is stable: routes/__init__.py still does
``from .er_copilot import router, public_router``.

Package ``router`` is ``crud.router`` (crud owns the empty-path collection
routes); every other submodule includes its router into it.
"""
from .crud import router
from .export import public_router, router as _export_router
from .notes import router as _notes_router
from .documents import router as _documents_router
from .analysis import router as _analysis_router
from .guidance import router as _guidance_router
from .search import router as _search_router
from .reports import router as _reports_router
from .case_views import router as _case_views_router

# Re-exported for tests that import these helpers directly from the package.
from ._shared import (
    _build_document_excerpts,
    _queue_risk_assessment_refresh,
    ER_DOC_PER_DOC_CHAR_CAP,
    ER_DOC_TOTAL_CHAR_CAP,
)

for _sub in (
    _export_router,
    _notes_router,
    _documents_router,
    _analysis_router,
    _guidance_router,
    _search_router,
    _reports_router,
    _case_views_router,
):
    router.include_router(_sub)

__all__ = [
    "router",
    "public_router",
    "_build_document_excerpts",
    "_queue_risk_assessment_refresh",
    "ER_DOC_PER_DOC_CHAR_CAP",
    "ER_DOC_TOTAL_CHAR_CAP",
]
