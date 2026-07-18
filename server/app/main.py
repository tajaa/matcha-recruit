import logging
import os
import time
import traceback as tb_module
from contextlib import asynccontextmanager

# WeasyPrint (used by /api/matcha-work/projects/{id}/export/pdf and the
# discipline signature flow) calls out to fontconfig, which writes its
# cache to ~/.cache/fontconfig. The matcha-backend container runs as uid
# 999 with HOME=/home/matcha — and that directory does not exist in the
# image — so fontconfig fails with "No writable cache directories" on
# every render. Point the cache at /tmp (writable, tmpfs in container)
# before any module imports WeasyPrint. Must run before fontconfig is
# initialized for the first time.
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")
os.environ.setdefault("HOME", "/tmp")
os.environ.setdefault("FONTCONFIG_PATH", "/etc/fonts")

# Configure the root logger so `logger = logging.getLogger(__name__)` calls
# inside app modules actually surface their INFO output. Uvicorn only sets
# up its own uvicorn / uvicorn.access loggers; without basicConfig here,
# every `logger.info` in services/routes falls through to the root logger
# at WARNING and gets silently dropped. Override with LOG_LEVEL env.
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
)

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from .config import get_settings, load_settings
from .core.services.error_reporter import install_error_logging, report_server_error
from .core.services.usage_tracker import (
    record_event,
    resolve_token,
    start_usage_flusher,
    stop_usage_flusher,
)
from .database import close_pool, get_connection, init_db, init_pool
from .core.services.notification_manager import (
    close_notification_manager,
    get_notification_manager,
    init_notification_manager,
)
from .core.services.redis_cache import close_redis_cache, init_redis_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = load_settings()
    print(f"[Matcha] Starting server on port {settings.port}")
    # Gemini client preference: matcha-work chat and most analyzers check
    # GEMINI_API_KEY first, falling back to the LIVE_API key in settings.
    _gemini_mode = (
        "Direct API (GEMINI_API_KEY set)"
        if os.getenv("GEMINI_API_KEY")
        else "Direct API (LIVE_API set)" if settings.gemini_api_key
        else "none configured — chat will fail"
    )
    print(f"[Matcha] Gemini client: {_gemini_mode}")

    # Initialize database
    await init_pool(settings.database_url, ssl_mode=settings.database_ssl)
    await init_db()
    print("[Matcha] Database initialized")

    # Install root logger handler that persists ERROR+ logs to server_error_reports.
    # Must run AFTER init_pool so the handler's first write has a working pool.
    install_error_logging(source="api")
    print("[Matcha] Server error reporter installed")

    # Recover documents stuck in 'processing' from a previous crash
    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE er_case_documents
            SET processing_status = 'failed',
                processing_error = 'Server restarted during processing. Please re-upload.'
            WHERE processing_status = 'processing'
            """
        )
        count = result.split()[-1] if result else "0"
        if count != "0":
            print(f"[Matcha] Recovered {count} stuck documents from previous crash")

    # Recover research tasks stuck in 'running' from a previous crash
    async with get_connection() as conn:
        stuck_projects = await conn.fetch(
            """SELECT id, project_data FROM mw_projects
               WHERE project_data::text LIKE '%"running"%'"""
        )
        recovered = 0
        for row in stuck_projects:
            data = row["project_data"] if isinstance(row["project_data"], dict) else {}
            changed = False
            for task in data.get("research_tasks", []):
                for inp in task.get("inputs", []):
                    if inp.get("status") == "running":
                        inp["status"] = "pending"
                        changed = True
                        recovered += 1
            if changed:
                import json as _json
                await conn.execute(
                    "UPDATE mw_projects SET project_data = $1::jsonb WHERE id = $2",
                    _json.dumps(data), row["id"],
                )
        if recovered:
            print(f"[Matcha] Reset {recovered} stuck research input(s) to pending")

    # Close out any broadcasts that were active when the server last crashed.
    # Any broadcast older than 6 hours is definitively dead (LiveKit auto-closes
    # empty rooms after empty_timeout; this just cleans up the DB row).
    # Tolerate missing table — `alembic upgrade head` may not have run yet.
    try:
        async with get_connection() as conn:
            stale = await conn.execute(
                """
                UPDATE channel_broadcasts
                SET ended_at = NOW()
                WHERE ended_at IS NULL
                  AND started_at < NOW() - INTERVAL '6 hours'
                """
            )
            count = stale.split()[-1] if stale else "0"
            if count != "0":
                print(f"[Matcha] Closed {count} stale broadcast(s) from previous run")
    except Exception as e:
        # UndefinedTableError when migration zzzz5d6e7f8g9 hasn't run yet.
        # Don't block boot — broadcast routes will surface a clear DB error.
        print(f"[Matcha] Skipping channel_broadcasts cleanup: {type(e).__name__}: {e}")

    # Initialize Redis notification manager (for worker task notifications)
    await init_notification_manager(settings.redis_url)
    print(f"[Matcha] Redis notification manager connected to {settings.redis_url}")

    # Initialize Redis cache
    await init_redis_cache(settings.redis_url)
    print("[Matcha] Redis cache initialized")

    # Start cross-worker channels-WS fanout subscriber + server-side keepalive.
    # Must run after init_redis_cache so the subscriber can immediately
    # connect. Both are per-worker tasks; with uvicorn --workers N they run
    # N times across the cluster, which is correct (each worker subscribes
    # and dispatches to its own local sockets).
    from .core.routes.channels_ws import (
        start_fanout_subscriber, start_server_ping_loop,
        stop_fanout_subscriber, stop_server_ping_loop,
    )
    start_fanout_subscriber()
    start_server_ping_loop()
    print("[Matcha] Channels WS fanout subscriber + keepalive ping started")

    # Same pattern for the matcha-work project presence WS — without this,
    # collaborators on different uvicorn workers don't see each other in the
    # project header pill (in-process ProjectConnectionManager dicts).
    from .matcha.routes.work.project_ws import (
        start_project_fanout_subscriber, stop_project_fanout_subscriber,
    )
    start_project_fanout_subscriber()
    print("[Matcha] Project WS fanout subscriber started")

    # Start channel inactivity checker (runs every 12h)
    from .core.services.inactivity_worker import start_inactivity_scheduler
    inactivity_task = await start_inactivity_scheduler()

    # Batched usage-event writer (per worker; each owns its own buffer).
    start_usage_flusher()
    print("[Matcha] Usage-event flusher started")

    yield

    # Cancel background tasks
    if inactivity_task:
        inactivity_task.cancel()

    await stop_fanout_subscriber()
    await stop_server_ping_loop()
    await stop_project_fanout_subscriber()
    # Drains whatever is still buffered (best-effort — analytics is droppable).
    await stop_usage_flusher()

    # Cleanup
    await close_redis_cache()
    await close_notification_manager()
    await close_pool()
    print("[Matcha] Server shutdown complete")


# Interactive API docs + OpenAPI schema enumerate every endpoint/param/model —
# a free attack-surface map. Expose them only in development.
_debug = os.getenv("DEBUG", "").lower() in ("1", "true")

app = FastAPI(
    title="Matcha Recruit API",
    description="AI-powered recruitment tool with voice interviews",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _debug else None,
    redoc_url="/redoc" if _debug else None,
    openapi_url="/openapi.json" if _debug else None,
)

# CORS - allow frontend dev server
_cors_kwargs: dict = dict(
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
        "https://hey-matcha.com",
        "https://www.hey-matcha.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Only allow the wildcard localhost regex in development
if _debug:
    _cors_kwargs["allow_origin_regex"] = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(CORSMiddleware, **_cors_kwargs)

# Trusted hosts — reject requests with spoofed Host headers. Static allowlist
# plus a dynamic fallback for Cappe custom domains (owners connect arbitrary
# domains that can't be enumerated here; the check hits a short-TTL cache over
# cappe_sites.custom_domain — see cappe/routes/render.py).
_ALLOWED_HOSTS = [
    "hey-matcha.com",
    "www.hey-matcha.com",
    "localhost",
    "127.0.0.1",
    "matcha-backend",
    # Cappe tenant subdomains (public sites served by the host-routed renderer).
    # Read from env directly: settings aren't loaded until lifespan startup.
    # Default base = main apex (site-x.hey-matcha.com) for MVP; the explicit
    # hey-matcha.com / www entries above keep the main app on exact-match.
    f"*.{os.getenv('CAPPE_BASE_DOMAIN', 'hey-matcha.com')}",
    # Cappe dedicated domain apex + www (the Gummfit landing/builder SPA calls
    # /api same-origin from the bare domain; harmless dup when base = main apex).
    os.getenv("CAPPE_BASE_DOMAIN", "hey-matcha.com"),
    f"www.{os.getenv('CAPPE_BASE_DOMAIN', 'hey-matcha.com')}",
    "*.cappe.localhost",
    "*.localhost",
    # Dev-only extra hosts (e.g. a webhook tunnel like *.trycloudflare.com).
    # Comma-separated env; unset in prod so the allowlist is unchanged.
    *[h.strip() for h in os.getenv("EXTRA_ALLOWED_HOSTS", "").split(",") if h.strip()],
]


def _host_in_allowlist(host: str) -> bool:
    for pattern in _ALLOWED_HOSTS:
        if host == pattern:
            return True
        if pattern.startswith("*") and host.endswith(pattern[1:]):
            return True
    return False


class DynamicTrustedHostMiddleware:
    """TrustedHostMiddleware semantics + an async DB-backed fallback for Cappe
    custom domains. Covers both HTTP and WebSocket scopes."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        host = ""
        for name, value in scope.get("headers") or []:
            if name == b"host":
                host = value.decode("latin-1").split(":", 1)[0].strip().lower().rstrip(".")
                break
        allowed = _host_in_allowlist(host)
        if not allowed and scope["type"] == "http":
            from .cappe.routes.render import is_registered_custom_domain
            allowed = await is_registered_custom_domain(host)
        if allowed:
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        from fastapi.responses import PlainTextResponse
        response = PlainTextResponse("Invalid host header", status_code=400)
        await response(scope, receive, send)


app.add_middleware(DynamicTrustedHostMiddleware)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Cappe published sites + their previews set their own tailored CSP at the
    # handler (cappe/routes/render.py:tenant_security_headers — they ship inline
    # widget scripts + Google Fonts, with all user content escaped/sanitized by
    # the renderer). Respect a handler-set policy; apply the strict app-wide
    # default everywhere else.
    if "Content-Security-Policy" not in response.headers:
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss: https:; "
            "font-src 'self' https:; "
            "frame-src 'self' https://*.cloudfront.net blob:; "
            "frame-ancestors 'none'"
        )
    return response


def _unwrap_excgroup(exc: BaseException) -> BaseException:
    """Unwrap nested BaseExceptionGroup to the deepest non-group inner.

    Starlette BaseHTTPMiddleware wraps downstream errors via
    anyio.create_task_group, so a TimeoutError from a route handler
    surfaces as BaseExceptionGroup([TimeoutError(...)]). Without this
    unwrap, error logs read `error_type=ExceptionGroup` with a
    traceback consisting entirely of Starlette/anyio plumbing — the
    real frames live inside `exc.exceptions[*]`.

    Falls back to the input if there is no group structure.
    """
    seen: set[int] = set()
    current: BaseException = exc
    while isinstance(current, BaseExceptionGroup) and current.exceptions:
        if id(current) in seen:
            break
        seen.add(id(current))
        current = current.exceptions[0]
    return current


def _format_exc_chain(exc: BaseException) -> str:
    """Format the unwrapped exception's traceback.

    Mirrors `traceback.format_exc()` for plain exceptions (the unwrap
    is a no-op there) and substitutes the inner exception's frames
    when ``exc`` is a BaseExceptionGroup.
    """
    inner = _unwrap_excgroup(exc)
    if inner is exc:
        return tb_module.format_exc()
    return "".join(tb_module.format_exception(type(inner), inner, inner.__traceback__))


# Paths that would either drown the table in noise or feed themselves:
# the beacon/error endpoints (self-reference), health checks (every few
# seconds), docs, and WS upgrades.
_USAGE_SKIP_PREFIXES = (
    "/health",
    "/api/usage",
    "/api/client-errors",
    "/api/admin/usage",
    "/docs",
    "/openapi",
    "/uploads",
    "/ws/",
)


@app.middleware("http")
async def track_api_usage(request: Request, call_next):
    """Record one usage_events row per API call (path template, status, duration).

    Deliberately never touches the response body — it only reads `status_code`
    after `call_next` — so SSE and StreamingResponse pass straight through
    unbuffered. For a stream, `duration_ms` is therefore time-to-first-byte, not
    total stream lifetime.
    """
    skip = request.method == "OPTIONS" or request.url.path.startswith(_USAGE_SKIP_PREFIXES)

    user_id = role = None
    if not skip:
        try:
            user_id, role = resolve_token(request.headers.get("authorization"))
            # Must happen BEFORE call_next: capture_errors reads request.state
            # in its exception path, i.e. while the route is still on the stack.
            if user_id:
                request.state.user_id = user_id
                request.state.user_role = role
        except Exception:
            pass  # analytics must never break a request

    start = time.perf_counter()
    response = await call_next(request)
    if skip:
        return response

    try:
        # The matched route's template (`/api/ir/incidents/{incident_id}`) keeps
        # cardinality bounded and ids out of the table. Unmatched requests are
        # mostly bot scans — collapse them all to one sentinel rather than
        # storing attacker-controlled paths.
        route = request.scope.get("route")
        path_template = getattr(route, "path_format", None) or "<unmatched>"

        record_event(
            surface="web",
            event="api_call",
            path=path_template,
            method=request.method,
            status=response.status_code,
            duration_ms=int((time.perf_counter() - start) * 1000),
            user_id=user_id,
            role=role,
        )
    except Exception:
        pass  # analytics must never break a response
    return response


@app.middleware("http")
async def capture_errors(request: Request, call_next):
    """Log unhandled exceptions to both the legacy error_logs table and the
    new server_error_reports table."""
    if request.url.path in ("/health", "/api/admin/error-logs", "/api/admin/server-errors"):
        return await call_next(request)
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        user_id = getattr(request.state, "user_id", None)
        user_role = getattr(request.state, "user_role", None)
        company_id = getattr(request.state, "company_id", None)
        real_exc = _unwrap_excgroup(exc)
        traceback_str = _format_exc_chain(exc)
        # Legacy error_logs insert (keeps existing admin page working)
        try:
            async with get_connection() as conn:
                await conn.execute(
                    """INSERT INTO error_logs
                       (method, path, status_code, error_type, error_message,
                        traceback, user_id, user_role, company_id, query_params)
                       VALUES ($1, $2, 500, $3, $4, $5, $6, $7, $8, $9)""",
                    request.method,
                    str(request.url.path),
                    type(real_exc).__name__,
                    str(real_exc)[:2000],
                    traceback_str[:8000],
                    user_id,
                    user_role,
                    company_id,
                    str(request.url.query) if request.url.query else None,
                )
        except Exception:
            logger.warning("Failed to persist error log", exc_info=True)
        # New structured reporter
        report_server_error(
            kind="http_error",
            message=f"{type(real_exc).__name__}: {real_exc}",
            exception=real_exc,
            traceback_str=traceback_str,
            source="api",
            request_method=request.method,
            request_path=str(request.url.path),
            request_status=500,
            user_id=str(user_id) if user_id else None,
            context={
                "user_role": user_role,
                "company_id": str(company_id) if company_id else None,
                "query": str(request.url.query) if request.url.query else None,
            },
        )
        raise


# Global exception handler — catches errors that FastAPI handles internally
# (e.g. route handler exceptions) before they become 500 responses.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Persist unhandled exceptions and return 500."""
    real_exc = _unwrap_excgroup(exc)
    traceback_str = _format_exc_chain(exc)
    logger.error("Unhandled %s on %s %s: %s", type(real_exc).__name__, request.method, request.url.path, real_exc)
    try:
        async with get_connection() as conn:
            await conn.execute(
                """INSERT INTO error_logs
                   (method, path, status_code, error_type, error_message,
                    traceback, query_params)
                   VALUES ($1, $2, 500, $3, $4, $5, $6)""",
                request.method,
                str(request.url.path),
                type(real_exc).__name__,
                str(real_exc)[:2000],
                traceback_str[:8000],
                str(request.url.query) if request.url.query else None,
            )
    except Exception:
        logger.warning("Failed to persist error log", exc_info=True)
    report_server_error(
        kind="http_error",
        message=f"{type(real_exc).__name__}: {real_exc}",
        exception=real_exc,
        traceback_str=traceback_str,
        source="api",
        request_method=request.method,
        request_path=str(request.url.path),
        request_status=500,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Import and include domain routers
from .core.routes import core_router, chat_ws_router, channels_ws_router
from .core.routes.stripe_webhook import router as stripe_webhook_router
from .matcha.routes import matcha_router
from .cappe.routes import cappe_router
from .tellus.routes import tellus_router

# Mount domain routers
app.include_router(core_router, prefix="/api")
app.include_router(matcha_router, prefix="/api")
# Cappe (website builder) — a separate product. Mounted standalone, NOT under
# matcha_router, so it bypasses the require_feature/company gate chain. Its own
# Cappe-scoped JWT auth gates per-endpoint.
app.include_router(cappe_router, prefix="/api/cappe")
# Tell-Us (rewards-for-feedback app) — a separate product, same pattern as Cappe.
# Mounted standalone, NOT under matcha_router, so it bypasses the
# require_feature/company gate chain. Its own tellus-scoped JWT gates per-endpoint.
app.include_router(tellus_router, prefix="/api/tellus")
# Webhook router under /api so prod nginx proxy_pass /api/ → backend works.
# Stripe dashboard endpoint must be https://hey-matcha.com/api/webhooks/stripe.
app.include_router(stripe_webhook_router, prefix="/api")

# WebSocket routes (separate prefix)
app.include_router(chat_ws_router, prefix="/ws/chat", tags=["chat-websocket"])
app.include_router(channels_ws_router, prefix="/ws/channels", tags=["channels-websocket"])

from .matcha.routes.work.thread_ws import router as thread_ws_router
app.include_router(thread_ws_router, prefix="/ws/threads", tags=["threads-websocket"])

from .matcha.routes.work.project_ws import router as project_ws_router
app.include_router(project_ws_router, prefix="/ws/projects", tags=["projects-websocket"])

# SEO routes — served at root, no /api prefix (crawlers expect /sitemap.xml + /robots.txt)
from .core.routes.sitemap import router as sitemap_router
app.include_router(sitemap_router, tags=["seo"])

# Cappe public-site renderer — served at root, host-gated to tenant subdomains
# (<sub>.cappe.hey-matcha.com / <sub>.cappe.localhost). Non-tenant hosts 404 here
# so /health, /sitemap.xml, /api/* etc. are unaffected.
from .cappe.routes.render import router as cappe_render_router
app.include_router(cappe_render_router, tags=["cappe-render"])


# Serve locally-uploaded files (logos, resumes, etc.) when S3 is not configured
_uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "matcha-recruit"}


@app.websocket("/ws/notifications")
async def notifications_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for receiving real-time task notifications.

    Clients can subscribe to channels by sending:
        {"action": "subscribe", "channel": "company:{company_id}"}

    They will receive notifications when worker tasks complete:
        {"type": "task_complete", "task_type": "interview_analysis", "entity_id": "...", "result": {...}}
    """
    await websocket.accept()
    manager = get_notification_manager()
    subscribed_channels: list[str] = []

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            channel = data.get("channel")

            if action == "subscribe" and channel:
                await manager.subscribe(websocket, channel)
                subscribed_channels.append(channel)
                await websocket.send_json({"type": "subscribed", "channel": channel})

            elif action == "unsubscribe" and channel:
                await manager.unsubscribe(websocket, channel)
                if channel in subscribed_channels:
                    subscribed_channels.remove(channel)
                await websocket.send_json({"type": "unsubscribed", "channel": channel})

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
