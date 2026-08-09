import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.oceanlab.routers._errors import OceanlabRoute
from app.oceanlab.db import get_db
from app.oceanlab.deps import AuthDep
from app.oceanlab.models.artist import Artist
from app.oceanlab.models.enums import ReleaseStatus
from app.oceanlab.models.release import Release, ReleaseArtist
from app.oceanlab.schemas.codes import AssignUpcResult
from app.oceanlab.schemas.common import Page
from app.oceanlab.schemas.release import (
    ReleaseArtistRead,
    ReleaseArtistsIn,
    ReleaseCreate,
    ReleaseRead,
    ReleaseUpdate,
)
from app.oceanlab.services import upc as upc_service
from app.oceanlab.services.defaults import apply_release_defaults

router = APIRouter(route_class=OceanlabRoute, prefix="/releases", tags=["releases"], dependencies=[AuthDep])


@router.get("", response_model=Page[ReleaseRead])
def list_releases(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: ReleaseStatus | None = None,
    artist_id: uuid.UUID | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = sa.select(Release)
    if status is not None:
        stmt = stmt.where(Release.status == status)
    if artist_id is not None:
        stmt = stmt.where(Release.primary_artist_id == artist_id)
    if q:
        stmt = stmt.where(Release.title.ilike(f"%{q}%"))
    total = db.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Release.title, Release.id).limit(limit).offset(offset)).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("", response_model=ReleaseRead, status_code=201)
def create_release(payload: ReleaseCreate, db: Session = Depends(get_db)):
    # Blank fields are filled from label settings (c-line, p-line, territories,
    # genre, label). An explicit value from the caller always wins.
    data = apply_release_defaults(db, payload.model_dump())
    if data.get("primary_artist_id") is None:
        raise HTTPException(
            status_code=422,
            detail="primary_artist_id is required (or set a default artist in label settings)",
        )
    release = Release(**data)
    db.add(release)
    db.commit()
    db.refresh(release)
    return release


@router.get("/{release_id}", response_model=ReleaseRead)
def get_release(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    return release


@router.patch("/{release_id}", response_model=ReleaseRead)
def update_release(release_id: uuid.UUID, payload: ReleaseUpdate, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(release, k, v)
    db.commit()
    db.refresh(release)
    return release


@router.delete("/{release_id}", status_code=204)
def delete_release(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    db.delete(release)
    db.commit()


@router.get("/{release_id}/artists", response_model=list[ReleaseArtistRead])
def list_release_artists(release_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(Release, release_id) is None:
        raise HTTPException(status_code=404, detail="Release not found")
    return db.execute(
        sa.select(ReleaseArtist)
        .where(ReleaseArtist.release_id == release_id)
        .order_by(ReleaseArtist.role, ReleaseArtist.position)
    ).scalars().all()


@router.put("/{release_id}/artists", response_model=list[ReleaseArtistRead])
def replace_release_artists(release_id: uuid.UUID, payload: ReleaseArtistsIn, db: Session = Depends(get_db)):
    """Replace-all the release's artist credits.

    Featured artists reach the packaging manifest's `featured_artists` column
    through this table; without this endpoint they were unreachable from the
    API entirely.
    """
    if db.get(Release, release_id) is None:
        raise HTTPException(status_code=404, detail="Release not found")

    # Pre-validate rather than leaning on the FK: an unknown artist_id would
    # otherwise surface as a 422 naming a constraint instead of the artist.
    for item in payload.artists:
        if db.get(Artist, item.artist_id) is None:
            raise HTTPException(status_code=422, detail=f"Artist not found: {item.artist_id}")

    db.execute(sa.delete(ReleaseArtist).where(ReleaseArtist.release_id == release_id))
    rows = [ReleaseArtist(release_id=release_id, **item.model_dump()) for item in payload.artists]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


@router.post("/{release_id}/assign-upc", response_model=AssignUpcResult)
def assign_upc(release_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        code = upc_service.assign_upc(db, release_id)
        db.commit()
    except upc_service.AlreadyAssigned as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    except upc_service.PoolEmpty as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    except upc_service.UpcError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e)) from e
    return AssignUpcResult(upc=code)
