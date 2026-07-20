"""Broker surfaces — HR-broker admin, client portfolio, submission packet, loss runs, Broker Pilot.

Namespace grouping: each module is an independent router with its own mount + gate in the
parent ``routes/__init__.py``; this package only re-exports them under their historical names.
"""

from .brokers import router as brokers_router
from .chat import router as broker_chat_router
from .external import router as broker_external_router
from .loss_runs import router as broker_loss_runs_router
from .pilot import router as broker_pilot_router
from .portfolio import router as broker_portfolio_router
from .submission import router as broker_submission_router
from .insurance import router as broker_insurance_router

__all__ = [
    "brokers_router",
    "broker_chat_router",
    "broker_external_router",
    "broker_loss_runs_router",
    "broker_pilot_router",
    "broker_portfolio_router",
    "broker_submission_router",
    "broker_insurance_router",
]
