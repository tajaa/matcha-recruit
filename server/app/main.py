from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import load_settings, get_settings
from .database import init_pool, init_db, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = load_settings()
    print(f"[Matcha] Starting server on port {settings.port}")
    print(f"[Matcha] Using {'Vertex AI' if settings.use_vertex else 'API Key'} for Gemini")

    # Initialize database
    await init_pool(settings.database_url)
    await init_db()

    yield

    # Cleanup
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
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from .routes import (
    companies_router,
    interviews_router,
    candidates_router,
    matching_router,
    positions_router,
    bulk_import_router,
    job_search_router,
    auth_router,
    openings_router,
    projects_router,
    outreach_router,
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
