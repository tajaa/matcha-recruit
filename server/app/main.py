import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.routers import artists, codes, contributors, health, recordings, releases, tracks, works
from app.routers._errors import integrity_error_to_http

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="oceanlab", version="0.1.0", lifespan=lifespan)


@app.exception_handler(IntegrityError)
async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.exception("IntegrityError on %s %s", request.method, request.url.path, exc_info=exc)
    http = integrity_error_to_http(exc)
    return JSONResponse(status_code=http.status_code, content={"detail": http.detail})


app.include_router(health.router, prefix="/api")
app.include_router(artists.router, prefix="/api")
app.include_router(contributors.router, prefix="/api")
app.include_router(works.router, prefix="/api")
app.include_router(recordings.router, prefix="/api")
app.include_router(releases.router, prefix="/api")
app.include_router(tracks.router, prefix="/api")
app.include_router(codes.router, prefix="/api")
