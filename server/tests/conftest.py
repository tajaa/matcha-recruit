"""Suite-wide test bootstrap.

**The google.genai import contract.**

Many modules under ``app/`` touch ``google.genai.types`` at *import* time
(``types.Tool(...)``, ``types.HarmCategory.HARM_CATEGORY_HARASSMENT``, ...).
Historically ~17 test modules each hand-rolled their own ``google.genai`` stub
via ``sys.modules.setdefault``, where each stub was a manually-curated allowlist
of only the attributes that module happened to need. Those stubs leak
process-wide: whichever test file imported first won, and any *later* test that
imported more of the route tree crashed on whatever that stub omitted. That is
exactly how the suite hit a total collection failure on
``types.HarmCategory``, and how ``test_matcha_work_image_generation`` passed in
isolation but failed in-suite (a stub's ``Part`` accepted no arguments).

This module replaces all of that with ONE strategy, applied before any ``app.``
import happens:

1. If the real SDK is installed (it is, and it is pinned in requirements.txt),
   just import it. Tests then run against the same types production does.
2. Otherwise install a *permissive* stub whose ``__getattr__`` synthesizes any
   attribute on demand. There is no allowlist to curate, so the next module-level
   ``genai`` attribute someone adds is immunized in advance rather than becoming
   the next suite-wide collection failure.

Neither branch performs network I/O: constructing types is inert, and no test
builds a real ``Client``.
"""

import sys
from types import ModuleType


class _Permissive:
    """Stands in for any google.genai type: constructible with any signature,
    callable, and yields another ``_Permissive`` for any attribute access — so
    ``types.HarmCategory.HARM_CATEGORY_HARASSMENT`` and
    ``types.Part.from_bytes(data=..., mime_type=...)`` both resolve."""

    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs

    def __call__(self, *args, **kwargs):
        return _Permissive(*args, **kwargs)

    def __getattr__(self, name):
        if name.startswith("__"):  # don't fake dunders — breaks copy/pickle/inspect
            raise AttributeError(name)
        return _Permissive()

    def __repr__(self):
        return "<google.genai stub>"


class _PermissiveModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = _Permissive()
        setattr(self, name, value)  # stable identity across lookups
        return value


def _install_genai() -> None:
    try:
        import google.genai  # noqa: F401
        import google.genai.types  # noqa: F401
    except Exception:
        google_module = sys.modules.get("google") or ModuleType("google")
        genai_module = _PermissiveModule("google.genai")
        types_module = _PermissiveModule("google.genai.types")
        genai_module.types = types_module
        genai_module.Client = _Permissive
        google_module.genai = genai_module
        sys.modules["google"] = google_module
        sys.modules["google.genai"] = genai_module
        sys.modules["google.genai.types"] = types_module


_install_genai()
