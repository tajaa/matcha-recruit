import logging
import os
import traceback as tb_module
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

logger = logging.getLogger(__name__)

from .config import get_settings, load_settings
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
    print(
        f"[Matcha] Using {'Vertex AI' if settings.use_vertex else 'API Key'} for Gemini"
    )

    # Initialize database
    await init_pool(settings.database_url, ssl_mode=settings.database_ssl)
    await init_db()
    print("[Matcha] Database initialized")

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

    # Initialize Redis notification manager (for worker task notifications)
    await init_notification_manager(settings.redis_url)
    print(f"[Matcha] Redis notification manager connected to {settings.redis_url}")

    # Initialize Redis cache
    await init_redis_cache(settings.redis_url)
    print("[Matcha] Redis cache initialized")

    yield

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
        "frame-ancestors 'none'"
    )
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def capture_errors(request: Request, call_next):
    """Log unhandled exceptions to the error_logs table."""
    if request.url.path in ("/health", "/api/admin/error-logs"):
        return await call_next(request)
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        # Extract user info from request state if auth middleware set it
        user_id = getattr(request.state, "user_id", None)
        user_role = getattr(request.state, "user_role", None)
        company_id = getattr(request.state, "company_id", None)
        traceback_str = tb_module.format_exc()
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
        raise


# Global exception handler — catches errors that FastAPI handles internally
# (e.g. route handler exceptions) before they become 500 responses.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Persist unhandled exceptions to error_logs and return 500."""
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
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Import and include domain routers
from .core.routes import core_router, chat_ws_router
from .core.routes.stripe_webhook import router as stripe_webhook_router
from .matcha.routes import matcha_router

# Mount domain routers
app.include_router(core_router, prefix="/api")
app.include_router(matcha_router, prefix="/api")
app.include_router(stripe_webhook_router)

# WebSocket routes (separate prefix)
app.include_router(chat_ws_router, prefix="/ws/chat", tags=["chat-websocket"])


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
