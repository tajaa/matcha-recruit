from fastapi import APIRouter

from . import artists, codes, contributors, health, recordings, releases, tracks, works

oceanlab_router = APIRouter(tags=["oceanlab"])
for _module in (health, artists, contributors, works, recordings, releases, tracks, codes):
    oceanlab_router.include_router(_module.router)
