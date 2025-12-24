from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings, load_settings
from .database import close_pool, init_db, init_pool
from .services.notification_manager import (
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from .routes import (
    auth_router,
    bulk_import_router,
    candidates_router,
    companies_router,
    interviews_router,
    job_search_router,
    matching_router,
    openings_router,
    outreach_router,
    positions_router,
    projects_router,
    public_jobs_router,
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(companies_router, prefix="/api/companies", tags=["companies"])
app.include_router(interviews_router, prefix="/api", tags=["interviews"])
app.include_router(candidates_router, prefix="/api/candidates", tags=["candidates"])
app.include_router(matching_router, prefix="/api", tags=["matching"])
app.include_router(positions_router, prefix="/api/positions", tags=["positions"])
app.include_router(bulk_import_router, prefix="/api/bulk", tags=["bulk-import"])
app.include_router(job_search_router, prefix="/api/jobs", tags=["job-search"])
app.include_router(openings_router, prefix="/api/openings", tags=["openings"])
app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(outreach_router, prefix="/api", tags=["outreach"])
app.include_router(public_jobs_router, prefix="/jobs", tags=["public-jobs"])


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
