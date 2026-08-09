"""Standalone oceanlab app.

Not mounted in production — the monolith mounts `oceanlab_router` directly
(see server/app/main.py, prefix /api/oceanlab). This module exists for the
oceanlab test suite (TestClient against unprefixed /api/* paths, matching
oceanlab's pre-monorepo test history) and for running oceanlab in isolation
during local development.

IntegrityError handling is scoped per-router via `OceanlabRoute`
(routers/_errors.py) rather than an app-level exception_handler, so the same
routers behave identically whether mounted here or in the monolith.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.oceanlab.config import ensure_storage_root
from app.oceanlab.routers import oceanlab_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_root()
    yield


app = FastAPI(title="oceanlab", version="0.1.0", lifespan=lifespan)
app.include_router(oceanlab_router, prefix="/api")
