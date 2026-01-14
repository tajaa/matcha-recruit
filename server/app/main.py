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
        "https://itsmatcha.net",
        "https://www.itsmatcha.net",
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
    contact_router,
    interviews_router,
    ir_incidents_router,
    job_search_router,
    matching_router,
    openings_router,
    outreach_router,
    positions_router,
    projects_router,
    public_jobs_router,
    offer_letters_router,
)
from .routes.leads_agent import router as leads_agent_router
from .routes.er_copilot import router as er_copilot_router
from .routes.policies import router as policies_router
from .routes.public_signatures import router as public_signatures_router
from .routes.compliance import router as compliance_router
from .routes.blog import router as blog_router
from .routes.employee_portal import router as employee_portal_router

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(companies_router, prefix="/api/companies", tags=["companies"])
app.include_router(candidates_router, prefix="/api/candidates", tags=["candidates"])
app.include_router(interviews_router, prefix="/api", tags=["interviews"])
app.include_router(matching_router, prefix="/api", tags=["matching"])
app.include_router(positions_router, prefix="/api/positions", tags=["positions"])
app.include_router(bulk_import_router, prefix="/api/bulk", tags=["bulk-import"])
app.include_router(job_search_router, prefix="/api/jobs", tags=["job-search"])
app.include_router(openings_router, prefix="/api/openings", tags=["openings"])
app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(outreach_router, prefix="/api", tags=["outreach"])
app.include_router(public_jobs_router, prefix="/api/job-board", tags=["public-jobs"])
app.include_router(contact_router, prefix="/api/contact", tags=["contact"])
app.include_router(er_copilot_router, prefix="/api/er/cases", tags=["er-copilot"])
app.include_router(ir_incidents_router, prefix="/api/ir/incidents", tags=["ir-incidents"])
app.include_router(leads_agent_router, prefix="/api/leads-agent", tags=["leads-agent"])
app.include_router(policies_router, prefix="/api", tags=["policies"])
app.include_router(public_signatures_router, prefix="/api", tags=["public-signatures"])
app.include_router(offer_letters_router, prefix="/api/offer-letters", tags=["offer-letters"])
app.include_router(compliance_router, prefix="/api/compliance", tags=["compliance"])
app.include_router(blog_router, prefix="/api/blogs", tags=["blog"])
app.include_router(employee_portal_router, prefix="/api/v1/portal", tags=["employee-portal"])


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
