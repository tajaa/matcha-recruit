"""Pure-helper tests for the error-reporter unwrap logic in app/main.py.

Starlette BaseHTTPMiddleware wraps downstream errors in a
BaseExceptionGroup via anyio.create_task_group. Without unwrapping
those, every admin error-log row reads `error_type=ExceptionGroup`
with a traceback consisting only of Starlette/anyio plumbing.

These tests pin the unwrap helper behavior in isolation — no app
boot, no DB.
"""

import sys
from types import ModuleType

# Stub google.genai before any app imports (matches other test files).
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

from app.main import _format_exc_chain, _unwrap_excgroup


class TestUnwrapExcGroup:
    def test_plain_exception_passthrough(self):
        exc = TimeoutError("expand timed out")
        assert _unwrap_excgroup(exc) is exc

    def test_single_excgroup_unwraps_inner(self):
        inner = ValueError("real cause")
        group = BaseExceptionGroup("wrapped", [inner])
        assert _unwrap_excgroup(group) is inner

    def test_nested_excgroup_unwraps_deepest(self):
        inner = RuntimeError("deep cause")
        mid = BaseExceptionGroup("mid", [inner])
        outer = BaseExceptionGroup("outer", [mid])
        assert _unwrap_excgroup(outer) is inner

    def test_first_inner_wins_when_group_has_multiple(self):
        first = ValueError("first")
        second = KeyError("second")
        group = BaseExceptionGroup("multi", [first, second])
        # Convention: the unwrap picks the first inner exception.
        assert _unwrap_excgroup(group) is first


class TestFormatExcChain:
    def test_plain_exception_uses_format_exc(self):
        # format_exc reads sys.exc_info, so format inside an except block.
        try:
            raise TimeoutError("test plain")
        except TimeoutError as exc:
            formatted = _format_exc_chain(exc)
            assert "TimeoutError" in formatted
            assert "test plain" in formatted

    def test_excgroup_formats_inner_traceback(self):
        try:
            raise RuntimeError("inner cause")
        except RuntimeError as inner:
            group = BaseExceptionGroup("starlette wrapper", [inner])
            formatted = _format_exc_chain(group)
            # Inner exception's type + message surface, not the group's.
            assert "RuntimeError" in formatted
            assert "inner cause" in formatted
