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

from fastapi import FastAPI

from app.oceanlab.routers import oceanlab_router

# No lifespan: object storage self-initializes on first use (services/storage.py
# get_store(), and LocalDiskStore creates its own root), so there is nothing to
# set up at boot. The monolith mounts oceanlab_router directly and never runs
# this module's lifespan anyway — anything put here would silently not run in
# prod, which is exactly the bug the storage_root mkdir used to be.
app = FastAPI(title="oceanlab", version="0.1.0")
app.include_router(oceanlab_router, prefix="/api")
