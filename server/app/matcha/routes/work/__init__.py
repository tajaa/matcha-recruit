"""Matcha-work web surfaces — journals, notifications, and the thread / project websockets.

Namespace grouping: each module is an independent router with its own mount + gate in the
parent ``routes/__init__.py``; this package only re-exports them under their historical names.
The websocket modules also expose non-router symbols (``thread_manager``,
``broadcast_task_event``, the project-fanout start/stop hooks) imported directly by module path
(``app.matcha.routes.work.thread_ws`` / ``.project_ws``) — this package does not front those.
"""

from .journals import router as journals_router
from .notifications import router as mw_notifications_router
from .project_ws import router as project_ws_router
from .thread_ws import router as thread_ws_router

__all__ = [
    "journals_router",
    "mw_notifications_router",
    "project_ws_router",
    "thread_ws_router",
]
