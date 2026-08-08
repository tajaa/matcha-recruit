"""Shared translation from SQLAlchemy IntegrityError to an HTTP response.

Branches on the underlying psycopg3 exception class so callers get a
consistent, correctly-coded response (409 for uniqueness conflicts, 422 for
FK/not-null violations) instead of ad-hoc, sometimes-wrong hard-coded
messages per endpoint.
"""

import logging

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from psycopg.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

# Friendly overrides for well-known unique constraints; falls back to a
# generic message built from the constraint name when not listed here.
_UNIQUE_CONSTRAINT_MESSAGES = {
    "uq_oceanlab_releases_upc": "UPC already in use",
    "uq_oceanlab_releases_catalog_number": "Catalog number already exists",
    "uq_oceanlab_artists_name": "Artist name already exists",
    "uq_oceanlab_works_iswc": "ISWC already exists",
    "uq_oceanlab_recordings_isrc": "ISRC already exists",
    "uq_oceanlab_tracks_release_disc_position": "Position already taken on this disc",
}


def integrity_error_to_http(e: IntegrityError) -> HTTPException:
    orig = e.orig
    if isinstance(orig, UniqueViolation):
        constraint = getattr(orig.diag, "constraint_name", None)
        message = _UNIQUE_CONSTRAINT_MESSAGES.get(constraint) or (
            f"Duplicate value violates {constraint}" if constraint else "Duplicate value violates a unique constraint"
        )
        return HTTPException(status_code=409, detail=message)
    if isinstance(orig, ForeignKeyViolation):
        constraint = getattr(orig.diag, "constraint_name", None)
        table = getattr(orig.diag, "table_name", None)
        # Discriminate by statement kind, not by parsing the (locale-dependent)
        # Postgres DETAIL string: a DELETE/UPDATE tripping a FK means the row is
        # still referenced (409); an INSERT/UPDATE tripping a FK means it points
        # at something that doesn't exist (422). SQLAlchemy always renders its
        # own SQL keywords in English regardless of server locale.
        statement = str(e.statement or "").strip().upper()
        if statement.startswith("DELETE"):
            what = table.replace("_", " ") if table else "other records"
            return HTTPException(status_code=409, detail=f"Cannot delete — still referenced by {what}")
        return HTTPException(status_code=422, detail=f"Referenced row does not exist ({constraint})")
    if isinstance(orig, NotNullViolation):
        col = getattr(orig.diag, "column_name", None)
        return HTTPException(status_code=422, detail=f"Field {col!r} cannot be null")
    return HTTPException(status_code=409, detail="Database integrity error")


class OceanlabRoute(APIRoute):
    """Route class that translates IntegrityError into an HTTP response.

    Scoped to oceanlab's own routers (via `APIRouter(route_class=OceanlabRoute)`)
    instead of a monolith-wide `app.exception_handler` — the monolith hosts
    other products whose IntegrityErrors must not be swallowed by oceanlab's
    translation rules.
    """

    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except IntegrityError as exc:
                logger.exception("IntegrityError on %s %s", request.method, request.url.path, exc_info=exc)
                http = integrity_error_to_http(exc)
                return JSONResponse(status_code=http.status_code, content={"detail": http.detail})

        return custom_route_handler
