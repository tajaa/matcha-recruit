"""Onboarding surfaces — new-hire task tracking + product-setup wizards (IR, Matcha-X) + invites.

Namespace grouping: each module is an independent router with its own mount + gate in the
parent ``routes/__init__.py``; this package only re-exports them under their historical names.
"""

from .new_hire import router as onboarding_router
from .ir import router as ir_onboarding_router
from .matcha_x import router as matcha_x_onboarding_router
from .invitations import router as invitations_router

__all__ = [
    "onboarding_router",
    "ir_onboarding_router",
    "matcha_x_onboarding_router",
    "invitations_router",
]
