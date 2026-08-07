"""Shared translation from SQLAlchemy IntegrityError to an HTTP response.

Branches on the underlying psycopg3 exception class so callers get a
consistent, correctly-coded response (409 for uniqueness conflicts, 422 for
FK/not-null violations) instead of ad-hoc, sometimes-wrong hard-coded
messages per endpoint.
"""

from psycopg.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

# Friendly overrides for well-known unique constraints; falls back to a
# generic message built from the constraint name when not listed here.
_UNIQUE_CONSTRAINT_MESSAGES = {
    "uq_releases_upc": "UPC already in use",
    "uq_releases_catalog_number": "Catalog number already exists",
    "uq_artists_name": "Artist name already exists",
    "uq_works_iswc": "ISWC already exists",
    "uq_recordings_isrc": "ISRC already exists",
    "uq_tracks_release_disc_position": "Position already taken on this disc",
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
        return HTTPException(status_code=422, detail=f"Referenced row does not exist ({constraint})")
    if isinstance(orig, NotNullViolation):
        col = getattr(orig.diag, "column_name", None)
        return HTTPException(status_code=422, detail=f"Field {col!r} cannot be null")
    return HTTPException(status_code=409, detail="Database integrity error")
