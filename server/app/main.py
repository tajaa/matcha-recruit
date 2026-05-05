import logging
import os
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

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

logger = logging.getLogger(__name__)

from .config import get_settings, load_settings
from .core.services.error_reporter import install_error_logging, report_server_error
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
    # GEMINI_API_KEY first and use direct API when set. Vertex is only used
    # as fallback when the API key is absent AND VERTEX_PROJECT is set.
    _gemini_mode = (
        "Direct API (GEMINI_API_KEY set)"
        if os.getenv("GEMINI_API_KEY")
        else "Vertex AI" if settings.use_vertex
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

    # Initialize Redis notification manager (for worker task notifications)
    await init_notification_manager(settings.redis_url)
    print(f"[Matcha] Redis notification manager connected to {settings.redis_url}")

    # Initialize Redis cache
    await init_redis_cache(settings.redis_url)
    print("[Matcha] Redis cache initialized")

    # Start channel inactivity checker (runs every 12h)
    from .core.services.inactivity_worker import start_inactivity_scheduler
    inactivity_task = await start_inactivity_scheduler()

    yield

    # Cancel background tasks
    if inactivity_task:
        inactivity_task.cancel()

    # Cleanup
    await close_redis_cache()
    await close_notification_manager()
    await close_pool()
    print("[Matcha] Server shutdown complete")


app = FastAPI(
    title="Matcha Recruit API",
    description="AI-powered recruitment tool with voice interviews",
    version="0.1.0",
    lifespan=lifespan,
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
if os.getenv("DEBUG", "").lower() in ("1", "true"):
    _cors_kwargs["allow_origin_regex"] = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(CORSMiddleware, **_cors_kwargs)

# Trusted hosts — reject requests with spoofed Host headers
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "hey-matcha.com",
        "www.hey-matcha.com",
        "localhost",
        "127.0.0.1",
        "matcha-backend",
    ],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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
        traceback_str = tb_module.format_exc()
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
                    type(exc).__name__,
                    str(exc)[:2000],
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
            message=f"{type(exc).__name__}: {exc}",
            exception=exc,
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
    traceback_str = tb_module.format_exc()
    logger.error("Unhandled %s on %s %s: %s", type(exc).__name__, request.method, request.url.path, exc)
    try:
        async with get_connection() as conn:
            await conn.execute(
                """INSERT INTO error_logs
                   (method, path, status_code, error_type, error_message,
                    traceback, query_params)
                   VALUES ($1, $2, 500, $3, $4, $5, $6)""",
                request.method,
                str(request.url.path),
                type(exc).__name__,
                str(exc)[:2000],
                traceback_str[:8000],
                str(request.url.query) if request.url.query else None,
            )
    except Exception:
        logger.warning("Failed to persist error log", exc_info=True)
    report_server_error(
        kind="http_error",
        message=f"{type(exc).__name__}: {exc}",
        exception=exc,
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

# Mount domain routers
app.include_router(core_router, prefix="/api")
app.include_router(matcha_router, prefix="/api")
# Webhook router under /api so prod nginx proxy_pass /api/ → backend works.
# Stripe dashboard endpoint must be https://hey-matcha.com/api/webhooks/stripe.
app.include_router(stripe_webhook_router, prefix="/api")

# WebSocket routes (separate prefix)
app.include_router(chat_ws_router, prefix="/ws/chat", tags=["chat-websocket"])
app.include_router(channels_ws_router, prefix="/ws/channels", tags=["channels-websocket"])

from .matcha.routes.thread_ws import router as thread_ws_router
app.include_router(thread_ws_router, prefix="/ws/threads", tags=["threads-websocket"])

# SEO routes — served at root, no /api prefix (crawlers expect /sitemap.xml + /robots.txt)
from .core.routes.sitemap import router as sitemap_router
app.include_router(sitemap_router, tags=["seo"])


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
