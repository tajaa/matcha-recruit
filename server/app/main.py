import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings, load_settings
from .database import close_pool, init_db, init_pool
from .core.services.notification_manager import (
    close_notification_manager,
    get_notification_manager,
    init_notification_manager,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = load_settings()
    print(f"[Matcha] Starting server on port {settings.port}")
    print(
        f"[Matcha] Using {'Vertex AI' if settings.use_vertex else 'API Key'} for Gemini"
    )

    # Initialize database
    await init_pool(settings.database_url)
    await init_db()
    print("[Matcha] Database initialized")


    # Initialize Redis notification manager (for worker task notifications)
    await init_notification_manager(settings.redis_url)
    print(f"[Matcha] Redis notification manager connected to {settings.redis_url}")

    yield

    # Cleanup
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "https://hey-matcha.com",
        "https://www.hey-matcha.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include domain routers
from .core.routes import core_router, chat_ws_router
from .matcha.routes import matcha_router

# Mount domain routers
app.include_router(core_router, prefix="/api")
app.include_router(matcha_router, prefix="/api")

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
