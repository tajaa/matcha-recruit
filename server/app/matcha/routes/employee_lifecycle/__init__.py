"""Employee-lifecycle surfaces — HR workflows that follow a worker from offer through separation.

Namespace grouping: each module is an independent router with its own mount + gate in the
parent ``routes/__init__.py``; this package only re-exports them under their historical names.
"""

from .cobra import router as cobra_router
from .flight_risk import router as flight_risk_router
from .i9 import router as i9_router
from .offer_letters import router as offer_letters_router, candidate_router as offer_letters_candidate_router
from .pre_termination import router as pre_termination_router
from .separation import router as separation_router
from .training import router as training_router

__all__ = [
    "cobra_router",
    "flight_risk_router",
    "i9_router",
    "offer_letters_router",
    "offer_letters_candidate_router",
    "pre_termination_router",
    "separation_router",
    "training_router",
]
