import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.oceanlab.routers._errors import OceanlabRoute
from app.oceanlab.db import get_db
from app.oceanlab.deps import AuthDep
from app.oceanlab.models.contributor import Contributor
from app.oceanlab.schemas.common import Page
from app.oceanlab.schemas.contributor import ContributorCreate, ContributorRead, ContributorUpdate

router = APIRouter(route_class=OceanlabRoute, prefix="/contributors", tags=["contributors"], dependencies=[AuthDep])


@router.get("", response_model=Page[ContributorRead])
def list_contributors(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = sa.select(Contributor)
    if q:
        stmt = stmt.where(Contributor.name.ilike(f"%{q}%"))
    total = db.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Contributor.name).limit(limit).offset(offset)).scalars().all()
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("", response_model=ContributorRead, status_code=201)
def create_contributor(payload: ContributorCreate, db: Session = Depends(get_db)):
    contributor = Contributor(**payload.model_dump())
    db.add(contributor)
    db.commit()
    db.refresh(contributor)
    return contributor


@router.get("/{contributor_id}", response_model=ContributorRead)
def get_contributor(contributor_id: uuid.UUID, db: Session = Depends(get_db)):
    contributor = db.get(Contributor, contributor_id)
    if contributor is None:
        raise HTTPException(status_code=404, detail="Contributor not found")
    return contributor


@router.patch("/{contributor_id}", response_model=ContributorRead)
def update_contributor(contributor_id: uuid.UUID, payload: ContributorUpdate, db: Session = Depends(get_db)):
    contributor = db.get(Contributor, contributor_id)
    if contributor is None:
        raise HTTPException(status_code=404, detail="Contributor not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(contributor, k, v)
    db.commit()
    db.refresh(contributor)
    return contributor


@router.delete("/{contributor_id}", status_code=204)
def delete_contributor(contributor_id: uuid.UUID, db: Session = Depends(get_db)):
    contributor = db.get(Contributor, contributor_id)
    if contributor is None:
        raise HTTPException(status_code=404, detail="Contributor not found")
    db.delete(contributor)
    db.commit()
