import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthDep
from app.models.work import Work, WorkWriter
from app.schemas.common import Page
from app.schemas.work import WorkCreate, WorkRead, WorkUpdate, WorkWriterIn, WorkWriterRead

router = APIRouter(tags=["works"], dependencies=[AuthDep])


@router.get("/works", response_model=Page[WorkRead])
def list_works(limit: int = 50, offset: int = 0, q: str | None = None, db: Session = Depends(get_db)):
    stmt = sa.select(Work)
    if q:
        stmt = stmt.where(Work.title.ilike(f"%{q}%"))
    total = db.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Work.title).limit(limit).offset(offset)).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("/works", response_model=WorkRead, status_code=201)
def create_work(payload: WorkCreate, db: Session = Depends(get_db)):
    work = Work(**payload.model_dump())
    db.add(work)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="ISWC already exists") from e
    db.refresh(work)
    return work


@router.get("/works/{work_id}", response_model=WorkRead)
def get_work(work_id: uuid.UUID, db: Session = Depends(get_db)):
    work = db.get(Work, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    return work


@router.patch("/works/{work_id}", response_model=WorkRead)
def update_work(work_id: uuid.UUID, payload: WorkUpdate, db: Session = Depends(get_db)):
    work = db.get(Work, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(work, k, v)
    db.commit()
    db.refresh(work)
    return work


@router.delete("/works/{work_id}", status_code=204)
def delete_work(work_id: uuid.UUID, db: Session = Depends(get_db)):
    work = db.get(Work, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    db.delete(work)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="Work is referenced by other records") from e


@router.put("/works/{work_id}/writers", response_model=list[WorkWriterRead])
def replace_writers(work_id: uuid.UUID, payload: list[WorkWriterIn], db: Session = Depends(get_db)):
    work = db.get(Work, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    db.execute(sa.delete(WorkWriter).where(WorkWriter.work_id == work_id))
    rows = []
    for item in payload:
        row = WorkWriter(work_id=work_id, **item.model_dump())
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows
