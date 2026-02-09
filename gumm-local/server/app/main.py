from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import load_settings
from .database import close_pool, init_db, init_pool
from .routes import router as local_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[gumm-local] Starting server on port {settings.port}")

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    await init_pool(settings.database_url)
    await init_db()
    print("[gumm-local] Database initialized")

    yield

    await close_pool()
    print("[gumm-local] Server shutdown complete")


app = FastAPI(
    title="gumm-local API",
    description="Cafe loyalty and local regulars management platform",
    version="0.1.0",
    lifespan=lifespan,
)

settings = load_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(local_router, prefix="/api", tags=["gumm-local"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "gumm-local"}
