from fastapi import APIRouter, Depends
from app.matcha.dependencies import require_feature

router = APIRouter(dependencies=[Depends(require_feature("matcha_work"))])
public_router = APIRouter()
presence_router = APIRouter()

from .presence import router as _presence_router

presence_router.include_router(_presence_router)

from . import _legacy

router.include_router(_legacy.router)
public_router.include_router(_legacy.public_router)

# Transitional re-export: test_language_tutor.py imports these constants
# directly from the package at module level. Plain string constants, so a
# package-level re-export is safe (no patch/mock semantics involved). Moves
# to a real submodule re-export when tutor.py is extracted (phase 15).
from ._legacy import (
    UTTERANCE_CHECK_PROMPT_EN,
    UTTERANCE_CHECK_PROMPT_ES,
    UTTERANCE_CHECK_PROMPT_FR,
)

__all__ = ["router", "public_router", "presence_router"]
