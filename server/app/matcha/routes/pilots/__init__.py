"""AI "pilot" builders — grounded chat / generation surfaces (analysis, handbook, legal defense).

Namespace grouping: each module is an independent router with its own mount + gate in the
parent ``routes/__init__.py``; this package only re-exports them under their historical names.
``legal_defense`` keeps its filename to match the ``legal_defense`` flag + ``legal_matter*`` tables.
"""

from .analysis import router as analysis_pilot_router
from .handbook import router as handbook_pilot_router
from .legal_defense import router as legal_defense_router, public_router as legal_defense_public_router

__all__ = [
    "analysis_pilot_router",
    "handbook_pilot_router",
    "legal_defense_router",
    "legal_defense_public_router",
]
