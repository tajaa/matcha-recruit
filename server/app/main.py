from fastapi import FastAPI

from app.routers import artists, codes, contributors, health, recordings, releases, tracks, works

app = FastAPI(title="oceanlab", version="0.1.0")

app.include_router(health.router, prefix="/api")
app.include_router(artists.router, prefix="/api")
app.include_router(contributors.router, prefix="/api")
app.include_router(works.router, prefix="/api")
app.include_router(recordings.router, prefix="/api")
app.include_router(releases.router, prefix="/api")
app.include_router(tracks.router, prefix="/api")
app.include_router(codes.router, prefix="/api")
