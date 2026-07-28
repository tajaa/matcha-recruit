"""Compliance Pilot — chat-driven library building for the admin Compliance Studio.

`core.py` is the original single-file service, unchanged in behavior: mode
templates, corpus builders, the one-JSON-turn chat, proposal resolution, the
deterministic `_codify_gate`, and the detached action runner.

This `__init__` re-exports exactly the surface the route
(`core/routes/admin_tools/admin_compliance_pilot.py`) imports, so the package
split is invisible to it — `from app.core.services import compliance_pilot as cp`
keeps working, as does the function-local `from ...compliance_pilot import
_codify_gate` (underscore-prefixed, so it must be named explicitly here; a
`from .core import *` would skip it).
"""
from app.core.services.compliance_pilot.core import (  # noqa: F401
    MAX_CONCURRENT_RESEARCH,
    MODEL,
    PILOT_TEMPLATES,
    STALE_RECLAIM_HOURS,
    _codify_gate,
    build_ask_corpus,
    build_scope_snapshot,
    default_categories,
    get_template,
    launch_action_task,
    resolve_proposal,
    run_action,
    run_chat_turn,
    template_catalog,
)

__all__ = [
    "MAX_CONCURRENT_RESEARCH",
    "MODEL",
    "PILOT_TEMPLATES",
    "STALE_RECLAIM_HOURS",
    "_codify_gate",
    "build_ask_corpus",
    "build_scope_snapshot",
    "default_categories",
    "get_template",
    "launch_action_task",
    "resolve_proposal",
    "run_action",
    "run_chat_turn",
    "template_catalog",
]
