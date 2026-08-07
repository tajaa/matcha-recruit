import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthDep
from app.models.codes import IsrcConfig, UpcCode
from app.models.enums import UpcStatus
from app.schemas.codes import IsrcConfigRead, IsrcConfigUpdate, UpcAddIn, UpcAddResult
from app.services import upc as upc_service

router = APIRouter(tags=["codes"], dependencies=[AuthDep])

_DEFAULT_ISRC_CONFIG = IsrcConfigRead(registrant_prefix="", year_digits="", next_designation=1)


@router.get("/settings/isrc", response_model=IsrcConfigRead)
def get_isrc_config(db: Session = Depends(get_db)):
    """Read-only: the id=1 row is seeded by migration, but if it's ever
    absent (e.g. a DB predating that migration), return the default shape
    rather than creating it as a side effect of a GET."""
    config = db.get(IsrcConfig, 1)
    if config is None:
        return _DEFAULT_ISRC_CONFIG
    return config


@router.put("/settings/isrc", response_model=IsrcConfigRead)
def update_isrc_config(payload: IsrcConfigUpdate, db: Session = Depends(get_db)):
    # Idempotent upsert so two concurrent first-writes can't race each other
    # into a duplicate-key 500 — the only place this router creates the row.
    stmt = pg_insert(IsrcConfig).values(
        id=1, registrant_prefix=payload.registrant_prefix, year_digits="", next_designation=1
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[IsrcConfig.id],
        set_={"registrant_prefix": stmt.excluded.registrant_prefix},
    )
    db.execute(stmt)
    db.commit()
    return db.get(IsrcConfig, 1)


@router.get("/upcs")
def list_upcs(db: Session = Depends(get_db)):
    rows = db.execute(sa.select(UpcCode).order_by(UpcCode.created_at)).scalars().all()
    return {
        "items": [{"id": r.id, "code": r.code, "status": r.status, "release_id": r.release_id} for r in rows],
        "available": sum(1 for r in rows if r.status == "available"),
        "assigned": sum(1 for r in rows if r.status == "assigned"),
    }


@router.post("/upcs", response_model=UpcAddResult)
def add_upcs(payload: UpcAddIn, db: Session = Depends(get_db)):
    added, rejected = upc_service.add_upcs(db, payload.codes)
    db.commit()
    return UpcAddResult(added=added, rejected=rejected)


@router.post("/upcs/{upc_id}/unassign", status_code=204)
def unassign_upc(upc_id: uuid.UUID, db: Session = Depends(get_db)):
    """Explicitly return a UPC to the available pool (deliberate action, e.g. after a release delete)."""
    upc = db.get(UpcCode, upc_id)
    if upc is None:
        raise HTTPException(status_code=404, detail="UPC not found")
    if upc.release_id is not None:
        from app.models.release import Release

        release = db.get(Release, upc.release_id)
        if release is not None and release.upc == upc.code:
            release.upc = None
    upc.status = UpcStatus.available
    upc.release_id = None
    upc.assigned_at = None
    db.commit()
