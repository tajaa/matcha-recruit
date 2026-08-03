"""RequestIDMiddleware — the per-request correlation ID (app/core/request_context.py).

Pure middleware unit tests against a minimal FastAPI app (no full app.main
boot, no DB) plus a direct test of the error_reporter context merge, which
reads the same contextvar outside of any request.
"""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.request_context import RequestIDMiddleware, request_id_var


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    async def ping():
        return {"request_id_seen_by_route": request_id_var.get()}

    return app


@pytest.mark.asyncio
async def test_response_carries_x_request_id_header():
    async with AsyncClient(transport=ASGITransport(app=_make_app()), base_url="http://test") as client:
        res = await client.get("/ping")
    assert res.status_code == 200
    rid = res.headers.get("x-request-id")
    assert rid
    assert rid != "-"


@pytest.mark.asyncio
async def test_two_requests_get_different_ids():
    async with AsyncClient(transport=ASGITransport(app=_make_app()), base_url="http://test") as client:
        first = await client.get("/ping")
        second = await client.get("/ping")
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


@pytest.mark.asyncio
async def test_valid_inbound_request_id_is_honored():
    async with AsyncClient(transport=ASGITransport(app=_make_app()), base_url="http://test") as client:
        res = await client.get("/ping", headers={"X-Request-ID": "client-supplied-id-123"})
    assert res.headers["x-request-id"] == "client-supplied-id-123"
    assert res.json()["request_id_seen_by_route"] == "client-supplied-id-123"


@pytest.mark.asyncio
async def test_invalid_inbound_request_id_is_replaced():
    async with AsyncClient(transport=ASGITransport(app=_make_app()), base_url="http://test") as client:
        # Too short (< 4 chars) — must not be trusted verbatim into logs/DB.
        res = await client.get("/ping", headers={"X-Request-ID": "ab"})
    assert res.headers["x-request-id"] != "ab"
    assert len(res.headers["x-request-id"]) >= 4


@pytest.mark.asyncio
async def test_contextvar_resets_after_request_so_requests_never_leak_ids():
    async with AsyncClient(transport=ASGITransport(app=_make_app()), base_url="http://test") as client:
        await client.get("/ping", headers={"X-Request-ID": "leaked-id-check"})
    # Outside any request/response cycle, the contextvar is back to default.
    assert request_id_var.get() == "-"


class TestErrorReporterContextMerge:
    """report_server_error() reads the same request_id_var directly (not via
    request.state — it has no Request object), so these are plain sync
    tests: no running event loop means report_server_error's own
    loop-detection takes the synchronous _upsert_sync_celery path, which we
    intercept before it touches the DB."""

    def test_merges_request_id_into_context_when_set(self, monkeypatch):
        import json

        from app.core.services import error_reporter

        captured = {}
        monkeypatch.setattr(
            error_reporter, "_upsert_sync_celery", lambda row: captured.setdefault("row", row)
        )

        token = request_id_var.set("test-rid-abc123")
        try:
            error_reporter.report_server_error(kind="exception", message="boom")
        finally:
            request_id_var.reset(token)

        context = json.loads(captured["row"]["context_json"])
        assert context["request_id"] == "test-rid-abc123"

    def test_no_request_id_key_when_unset(self, monkeypatch):
        import json

        from app.core.services import error_reporter

        assert request_id_var.get() == "-"  # sanity: no leakage from the prior test

        captured = {}
        monkeypatch.setattr(
            error_reporter, "_upsert_sync_celery", lambda row: captured.setdefault("row", row)
        )

        error_reporter.report_server_error(kind="exception", message="boom, no request context")

        context = (
            json.loads(captured["row"]["context_json"]) if captured["row"]["context_json"] else {}
        )
        assert "request_id" not in context


def test_request_id_middleware_is_outermost_in_the_real_app():
    """Registered LAST in main.py so Starlette (which wraps user middleware in
    reverse registration order) makes it OUTERMOST — the contextvar must be
    set before capture_errors, track_api_usage, or any route code runs. If
    this ever regresses, request_id disappears from logs/error rows for
    exactly the exceptions that matter most (the ones other middleware raises
    before this one would otherwise see them)."""
    import app.main as main_module

    names = [mw.cls.__name__ for mw in main_module.app.user_middleware]
    assert names[0] == "RequestIDMiddleware", (
        f"expected RequestIDMiddleware outermost (first in user_middleware), got: {names}"
    )
