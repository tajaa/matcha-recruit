"""Drift guard for the shared display-name helper in app.werk.routes._shared.

The NULLIF+BTRIM wrap is load-bearing (see _shared.py's docstring comment) —
without it, an admin-only user (no matching `employees` row) renders as a
blank name. This test fails loudly if a future edit reintroduces the raw
`CONCAT(e.first_name, ' ', e.last_name)` form anywhere the four route modules
resolve a display name, or if a module stops importing the shared helper.
"""

import sys
from types import ModuleType

import pytest

# ── Stub google.genai before importing app code ──
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)


def test_shared_expr_has_nullif_btrim_wrap():
    from app.werk.routes._shared import _USER_NAME_EXPR

    assert "NULLIF(BTRIM(CONCAT(" in _USER_NAME_EXPR


@pytest.mark.parametrize(
    "modname",
    [
        "app.werk.routes.channel_calls",
        "app.werk.routes.channel_broadcasts",
        "app.werk.routes.inbox",
        "app.werk.routes.channel_job_postings",
    ],
)
def test_route_module_imports_shared_resolve_display_name(modname):
    import importlib
    from app.werk.routes._shared import resolve_display_name as shared_fn

    mod = importlib.import_module(modname)
    assert getattr(mod, "resolve_display_name", None) is shared_fn, (
        f"{modname} must import resolve_display_name from ._shared, not "
        "reimplement its own raw COALESCE(...) name query"
    )
