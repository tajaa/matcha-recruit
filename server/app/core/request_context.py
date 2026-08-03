"""Per-request correlation ID — stitches one browser action across the app
log lines, the X-Request-ID response header, and the resulting
server_error_reports row.

Pure ASGI middleware (not BaseHTTPMiddleware): no response-body buffering,
covers WebSocket scopes too, and the contextvar it sets survives into every
downstream handler/exception path on the same connection — including
Celery's `logger.error`/`report_server_error` calls, which simply see the
default "-" since they run in a separate worker process with no request.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Inbound X-Request-ID is attacker-controlled (any client can set it) and
# lands in server_error_reports.context — validate before trusting it.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{4,64}$")


def _new_request_id() -> str:
    return uuid.uuid4().hex[:8]


class RequestIDMiddleware:
    """Assigns (or honors, if valid) a request ID for the lifetime of one
    ASGI connection, exposes it via the request_id_var contextvar, and
    stamps it on the response as X-Request-ID.

    Registered LAST in main.py so it ends up OUTERMOST (Starlette wraps
    user middleware in reverse registration order) — the contextvar must be
    set before capture_errors, track_api_usage, or any route code runs, so
    every log line and error report for this connection can see it.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        inbound = None
        for name, value in scope.get("headers") or []:
            if name == b"x-request-id":
                candidate = value.decode("latin-1").strip()
                if _VALID_REQUEST_ID.match(candidate):
                    inbound = candidate
                break

        request_id = inbound or _new_request_id()
        token = request_id_var.set(request_id)
        try:
            if scope["type"] == "websocket":
                await self.app(scope, receive, send)
                return

            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers["X-Request-ID"] = request_id
                await send(message)

            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)
