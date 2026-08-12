import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.oceanlab.routers._errors import OceanlabRoute
from app.oceanlab.db import get_db
from app.oceanlab.deps import AuthDep
from app.oceanlab.models.recording import Credit, MasterSplit, Recording
from app.oceanlab.models.work import RecordingWork, Work
from app.oceanlab.schemas.codes import AssignIsrcResult
from app.oceanlab.schemas.common import Page
from app.oceanlab.schemas.recording import (
    CreditIn,
    CreditRead,
    MasterSplitIn,
    MasterSplitRead,
    RecordingCreate,
    RecordingRead,
    RecordingUpdate,
    WorkLinksIn,
)
from app.oceanlab.schemas.work import WorkRead
from app.oceanlab.services import isrc as isrc_service
from app.oceanlab.services.defaults import seed_recording_ownership

router = APIRouter(
    route_class=OceanlabRoute,
    prefix="/recordings",
    tags=["recordings"],
    dependencies=[AuthDep],
)


@router.get("", response_model=Page[RecordingRead])
def list_recordings(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = sa.select(Recording)
    if q:
        stmt = stmt.where(Recording.title.ilike(f"%{q}%"))
    total = db.execute(
        sa.select(sa.func.count()).select_from(stmt.subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Recording.title, Recording.id).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("", response_model=RecordingRead, status_code=201)
def create_recording(payload: RecordingCreate, db: Session = Depends(get_db)):
    recording = Recording(**payload.model_dump())
    db.add(recording)
    db.flush()
    # Single-owner label: give it its 100% master split and matching work now,
    # as real editable rows. No-op when no default contributor is configured.
    seed_recording_ownership(db, recording)
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
def update_recording(
    recording_id: uuid.UUID, payload: RecordingUpdate, db: Session = Depends(get_db)
):
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
    db.commit()


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
def replace_splits(
    recording_id: uuid.UUID, payload: list[MasterSplitIn], db: Session = Depends(get_db)
):
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    db.execute(sa.delete(MasterSplit).where(MasterSplit.recording_id == recording_id))
    rows = [
        MasterSplit(recording_id=recording_id, **item.model_dump()) for item in payload
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


@router.get("/{recording_id}/splits", response_model=list[MasterSplitRead])
def list_splits(recording_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(Recording, recording_id) is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    return (
        db.execute(
            sa.select(MasterSplit)
            .where(MasterSplit.recording_id == recording_id)
            .order_by(MasterSplit.id)
        )
        .scalars()
        .all()
    )


@router.put("/{recording_id}/credits", response_model=list[CreditRead])
def replace_credits(
    recording_id: uuid.UUID, payload: list[CreditIn], db: Session = Depends(get_db)
):
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


@router.get("/{recording_id}/credits", response_model=list[CreditRead])
def list_credits(recording_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(Recording, recording_id) is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    return db.scalars(
        sa.select(Credit).where(Credit.recording_id == recording_id).order_by(Credit.position, Credit.id)
    ).all()


@router.put("/{recording_id}/works")
def replace_works(
    recording_id: uuid.UUID, payload: WorkLinksIn, db: Session = Depends(get_db)
):
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    db.execute(
        sa.delete(RecordingWork).where(RecordingWork.recording_id == recording_id)
    )
    for work_id in payload.work_ids:
        db.add(RecordingWork(recording_id=recording_id, work_id=work_id))
    db.commit()
    return {"work_ids": payload.work_ids}


@router.get("/{recording_id}/works", response_model=list[WorkRead])
def list_works(recording_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(Recording, recording_id) is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    return (
        db.execute(
            sa.select(Work)
            .join(RecordingWork, RecordingWork.work_id == Work.id)
            .where(RecordingWork.recording_id == recording_id)
            .order_by(Work.title, Work.id)
        )
        .scalars()
        .all()
    )
