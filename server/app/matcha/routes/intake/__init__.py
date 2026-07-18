"""Public intake surfaces — anonymous report + magic-link forms, off-platform client intake.

Namespace grouping: each module is an independent router with its own mount (no auth / no feature
gate; token-validated internally) in the parent ``routes/__init__.py``; this package only
re-exports them under their historical names.
"""

from .inbound_email import router as anonymous_report_router
from .external import router as external_intake_router

__all__ = [
    "anonymous_report_router",
    "external_intake_router",
]
