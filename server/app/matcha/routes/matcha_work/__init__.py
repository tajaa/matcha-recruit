from fastapi import APIRouter, Depends
from app.matcha.dependencies import require_feature

router = APIRouter(dependencies=[Depends(require_feature("matcha_work"))])
public_router = APIRouter()
presence_router = APIRouter()

from .presence import router as _presence_router

presence_router.include_router(_presence_router)

from .pdf_export import router as _pdf_export_router

router.include_router(_pdf_export_router)

from .thread_uploads import router as _thread_uploads_router

router.include_router(_thread_uploads_router)

from .projects import router as _projects_router, public_router as _projects_public

router.include_router(_projects_router)
public_router.include_router(_projects_public)

from .sections import router as _sections_router

router.include_router(_sections_router)

from .tasks import router as _tasks_router

router.include_router(_tasks_router)

from .workspace import router as _workspace_router

router.include_router(_workspace_router)

from .elements import router as _elements_router

router.include_router(_elements_router)

from .github import router as _github_router, public_router as _github_public

router.include_router(_github_router)
public_router.include_router(_github_public)

from .collaboration import router as _collaboration_router

router.include_router(_collaboration_router)

from .recruiting import router as _recruiting_router

router.include_router(_recruiting_router)

from .tutor import router as _tutor_router

router.include_router(_tutor_router)

from . import _legacy

router.include_router(_legacy.router)
public_router.include_router(_legacy.public_router)

__all__ = ["router", "public_router", "presence_router"]
