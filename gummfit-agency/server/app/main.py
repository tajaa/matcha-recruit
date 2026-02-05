from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings, load_settings
from .database import close_pool, init_db, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = load_settings()
    print(f"[Gummfit] Starting server on port {settings.port}")

    # Initialize database
    await init_pool(settings.database_url)
    await init_db()
    print("[Gummfit] Database initialized")

    yield

    # Cleanup
    await close_pool()
    print("[Gummfit] Server shutdown complete")


app = FastAPI(
    title="Gummfit Agency API",
    description="Creator economy platform — agencies, creators, deals, campaigns",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:3000",
        "https://hey-matcha.com",
        "https://www.hey-matcha.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes
from .routes.auth import router as auth_router
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# Gummfit domain routes
from .gummfit.routes import gummfit_router
app.include_router(gummfit_router, prefix="/api", tags=["gummfit"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "gummfit-agency"}
