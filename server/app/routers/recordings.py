import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthDep
from app.models.recording import Credit, MasterSplit, Recording
from app.models.work import RecordingWork
from app.schemas.codes import AssignIsrcResult
from app.schemas.common import Page
from app.schemas.recording import (
    CreditIn,
    CreditRead,
    MasterSplitIn,
    MasterSplitRead,
    RecordingCreate,
    RecordingRead,
    RecordingUpdate,
    WorkLinksIn,
)
from app.services import isrc as isrc_service

router = APIRouter(prefix="/recordings", tags=["recordings"], dependencies=[AuthDep])


@router.get("", response_model=Page[RecordingRead])
def list_recordings(limit: int = 50, offset: int = 0, q: str | None = None, db: Session = Depends(get_db)):
    stmt = sa.select(Recording)
    if q:
        stmt = stmt.where(Recording.title.ilike(f"%{q}%"))
    total = db.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Recording.title).limit(limit).offset(offset)).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("", response_model=RecordingRead, status_code=201)
def create_recording(payload: RecordingCreate, db: Session = Depends(get_db)):
    recording = Recording(**payload.model_dump())
    db.add(recording)
    db.commit()
    db.refresh(recording)
    return recording


@router.get("/{recording_id}", response_model=RecordingRead)
def get_recording(recording_id: uuid.UUID, db: Session = Depends(get_db)):
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    return recording


@router.patch("/{recording_id}", response_model=RecordingRead)
def update_recording(recording_id: uuid.UUID, payload: RecordingUpdate, db: Session = Depends(get_db)):
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(recording, k, v)
    db.commit()
    db.refresh(recording)
    return recording


@router.delete("/{recording_id}", status_code=204)
def delete_recording(recording_id: uuid.UUID, db: Session = Depends(get_db)):
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    db.delete(recording)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="Recording is referenced by other records") from e


@router.post("/{recording_id}/assign-isrc", response_model=AssignIsrcResult)
def assign_isrc(recording_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        isrc = isrc_service.assign_isrc(db, recording_id)
        db.commit()
    except isrc_service.AlreadyAssigned as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    except isrc_service.IsrcError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e)) from e
    return AssignIsrcResult(isrc=isrc)


@router.put("/{recording_id}/splits", response_model=list[MasterSplitRead])
def replace_splits(recording_id: uuid.UUID, payload: list[MasterSplitIn], db: Session = Depends(get_db)):
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    db.execute(sa.delete(MasterSplit).where(MasterSplit.recording_id == recording_id))
    rows = [MasterSplit(recording_id=recording_id, **item.model_dump()) for item in payload]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


@router.put("/{recording_id}/credits", response_model=list[CreditRead])
def replace_credits(recording_id: uuid.UUID, payload: list[CreditIn], db: Session = Depends(get_db)):
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    db.execute(sa.delete(Credit).where(Credit.recording_id == recording_id))
    rows = [Credit(recording_id=recording_id, **item.model_dump()) for item in payload]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


@router.put("/{recording_id}/works")
def replace_works(recording_id: uuid.UUID, payload: WorkLinksIn, db: Session = Depends(get_db)):
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    db.execute(sa.delete(RecordingWork).where(RecordingWork.recording_id == recording_id))
    for work_id in payload.work_ids:
        db.add(RecordingWork(recording_id=recording_id, work_id=work_id))
    db.commit()
    return {"work_ids": payload.work_ids}
