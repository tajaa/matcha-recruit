import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthDep
from app.models.enums import ReleaseStatus
from app.models.release import Release
from app.routers._errors import integrity_error_to_http
from app.schemas.codes import AssignUpcResult
from app.schemas.common import Page
from app.schemas.release import ReleaseCreate, ReleaseRead, ReleaseUpdate
from app.services import upc as upc_service

router = APIRouter(prefix="/releases", tags=["releases"], dependencies=[AuthDep])


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
    rows = db.execute(stmt.order_by(Release.title).limit(limit).offset(offset)).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("", response_model=ReleaseRead, status_code=201)
def create_release(payload: ReleaseCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    if data.get("label_name") is None:
        data.pop("label_name")
    release = Release(**data)
    db.add(release)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise integrity_error_to_http(e) from e
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
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise integrity_error_to_http(e) from e
    db.refresh(release)
    return release


@router.delete("/{release_id}", status_code=204)
def delete_release(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    db.delete(release)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="Release is referenced by other records") from e


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
