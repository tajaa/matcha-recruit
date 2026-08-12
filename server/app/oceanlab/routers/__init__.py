from fastapi import APIRouter

from . import artists, auth, codes, contributors, health, ingest, recordings, releases, tracks, works

oceanlab_router = APIRouter(tags=["oceanlab"])
for _module in (auth, health, artists, contributors, works, recordings, releases, tracks, codes, ingest):
    oceanlab_router.include_router(_module.router)
