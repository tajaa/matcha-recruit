"""Unhandled-exception reporting — no double-persist, no missing traceback.

Before this fix, a route exception that reached both `capture_errors`
(middleware) and `unhandled_exception_handler` (the ExceptionMiddleware
handler — the "response already started, re-raise" case) was logged and
persisted to server_error_reports TWICE, under two different `kind`
classifications, and neither stdout log line carried a traceback. These
tests pin the fix: `request.state.error_reported` makes the second path a
no-op, and the log calls pass `exc_info` so `docker logs` gets the trace.

No app boot, no DB — matches the app.main test convention in
test_main_middleware.py (google.genai stub, direct function import).
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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

import app.main as main_module


class _FakeConn:
    async def execute(self, *args, **kwargs):
        return None


class _FakeConnCtx:
    async def __aenter__(self):
        return _FakeConn()

    async def __aexit__(self, *exc):
        return False


def _fake_request(path: str = "/api/whatever") -> SimpleNamespace:
    url = SimpleNamespace(path=path, query="")
    return SimpleNamespace(state=SimpleNamespace(), url=url, method="GET")


@pytest.fixture(autouse=True)
def _patch_db_and_reporter(monkeypatch):
    monkeypatch.setattr(main_module, "get_connection", lambda *a, **kw: _FakeConnCtx())
    mock_report = MagicMock()
    monkeypatch.setattr(main_module, "report_server_error", mock_report)
    return mock_report


class TestCaptureErrorsDedupe:
    @pytest.mark.asyncio
    async def test_reports_once_and_reraises(self, _patch_db_and_reporter):
        request = _fake_request()

        async def call_next(_req):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await main_module.capture_errors(request, call_next)

        assert _patch_db_and_reporter.call_count == 1
        assert request.state.error_reported is True

    @pytest.mark.asyncio
    async def test_skips_second_report_when_already_reported(self, _patch_db_and_reporter):
        request = _fake_request()
        request.state.error_reported = True  # set by unhandled_exception_handler already

        async def call_next(_req):
            raise RuntimeError("boom again")

        with pytest.raises(RuntimeError):
            await main_module.capture_errors(request, call_next)

        # Exception still propagates (ASGI needs to see it), but no second persist.
        _patch_db_and_reporter.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_health_and_admin_error_paths(self, _patch_db_and_reporter):
        for path in ("/health", "/api/admin/error-logs", "/api/admin/server-errors"):
            request = _fake_request(path)
            called = {"value": False}

            async def call_next(_req):
                called["value"] = True
                return "ok"

            result = await main_module.capture_errors(request, call_next)
            assert result == "ok"
            assert called["value"] is True
        _patch_db_and_reporter.assert_not_called()


class TestUnhandledExceptionHandlerDedupe:
    @pytest.mark.asyncio
    async def test_reports_once_and_marks_state(self, _patch_db_and_reporter):
        request = _fake_request()
        exc = ValueError("route blew up")

        response = await main_module.unhandled_exception_handler(request, exc)

        assert response.status_code == 500
        assert _patch_db_and_reporter.call_count == 1
        assert request.state.error_reported is True

    @pytest.mark.asyncio
    async def test_skips_second_report_when_already_reported(self, _patch_db_and_reporter):
        request = _fake_request()
        request.state.error_reported = True  # set by capture_errors already

        response = await main_module.unhandled_exception_handler(request, ValueError("boom"))

        assert response.status_code == 500
        _patch_db_and_reporter.assert_not_called()
