import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.oceanlab.routers._errors import OceanlabRoute
from app.oceanlab.db import get_db
from app.oceanlab.deps import AuthDep
from app.oceanlab.models.artist import Artist
from app.oceanlab.schemas.artist import ArtistCreate, ArtistRead, ArtistUpdate
from app.oceanlab.schemas.common import Page

router = APIRouter(route_class=OceanlabRoute, prefix="/artists", tags=["artists"], dependencies=[AuthDep])


@router.get("", response_model=Page[ArtistRead])
def list_artists(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = sa.select(Artist)
    if q:
        stmt = stmt.where(Artist.name.ilike(f"%{q}%"))
    total = db.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Artist.name).limit(limit).offset(offset)).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("", response_model=ArtistRead, status_code=201)
def create_artist(payload: ArtistCreate, db: Session = Depends(get_db)):
    artist = Artist(**payload.model_dump())
    db.add(artist)
    db.commit()
    db.refresh(artist)
    return artist


@router.get("/{artist_id}", response_model=ArtistRead)
def get_artist(artist_id: uuid.UUID, db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    return artist


@router.patch("/{artist_id}", response_model=ArtistRead)
def update_artist(artist_id: uuid.UUID, payload: ArtistUpdate, db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(artist, k, v)
    db.commit()
    db.refresh(artist)
    return artist


@router.delete("/{artist_id}", status_code=204)
def delete_artist(artist_id: uuid.UUID, db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    db.delete(artist)
    db.commit()
