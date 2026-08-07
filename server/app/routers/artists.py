import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthDep
from app.models.artist import Artist
from app.schemas.artist import ArtistCreate, ArtistRead, ArtistUpdate
from app.schemas.common import Page

router = APIRouter(prefix="/artists", tags=["artists"], dependencies=[AuthDep])


@router.get("", response_model=Page[ArtistRead])
def list_artists(limit: int = 50, offset: int = 0, q: str | None = None, db: Session = Depends(get_db)):
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
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="Artist name already exists") from e
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
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="Artist name already exists") from e
    db.refresh(artist)
    return artist


@router.delete("/{artist_id}", status_code=204)
def delete_artist(artist_id: uuid.UUID, db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    db.delete(artist)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="Artist is referenced by other records") from e
