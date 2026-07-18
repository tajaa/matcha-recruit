"""External integrations + inbound webhooks — Google/Slack provisioning, Twilio voice, mock HRIS.

Namespace grouping: each module is an independent router with its own mount + gate in the
parent ``routes/__init__.py``; this package only re-exports them under their historical names.
"""

from .fake_hris import router as fake_hris_router
from .provisioning import router as provisioning_router
from .twilio_webhook import router as twilio_webhook_router

__all__ = [
    "fake_hris_router",
    "provisioning_router",
    "twilio_webhook_router",
]
