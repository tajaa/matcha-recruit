import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.oceanlab.routers._errors import OceanlabRoute
from app.oceanlab.db import get_db
from app.oceanlab.deps import AuthDep
from app.oceanlab.models.artist import Artist
from app.oceanlab.models.codes import IsrcConfig, UpcCode
from app.oceanlab.models.contributor import Contributor
from app.oceanlab.models.enums import UpcStatus
from app.oceanlab.models.release import Release
from app.oceanlab.schemas.codes import IsrcConfigRead, IsrcConfigUpdate, UpcAddIn, UpcAddResult, UpcListResponse
from app.oceanlab.schemas.settings import LabelSettingsRead, LabelSettingsUpdate
from app.oceanlab.services import upc as upc_service
from app.oceanlab.services.defaults import get_label_settings

router = APIRouter(route_class=OceanlabRoute, tags=["codes"], dependencies=[AuthDep])

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


@router.get("/settings/label", response_model=LabelSettingsRead)
def get_label_settings_route(db: Session = Depends(get_db)):
    settings_row = get_label_settings(db)
    db.commit()  # get_label_settings upserts the singleton if it's missing
    return settings_row


@router.put("/settings/label", response_model=LabelSettingsRead)
def update_label_settings(payload: LabelSettingsUpdate, db: Session = Depends(get_db)):
    settings_row = get_label_settings(db)

    changes = payload.model_dump(exclude_unset=True)
    # Pre-validate the two FKs so an unknown id reads as "Artist not found"
    # rather than a constraint name.
    if changes.get("default_artist_id") is not None and db.get(Artist, changes["default_artist_id"]) is None:
        raise HTTPException(status_code=422, detail=f"Artist not found: {changes['default_artist_id']}")
    if (
        changes.get("default_contributor_id") is not None
        and db.get(Contributor, changes["default_contributor_id"]) is None
    ):
        raise HTTPException(status_code=422, detail=f"Contributor not found: {changes['default_contributor_id']}")

    for key, value in changes.items():
        setattr(settings_row, key, value)
    db.commit()
    db.refresh(settings_row)
    return settings_row


@router.get("/upcs", response_model=UpcListResponse)
def list_upcs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    counts = dict(db.execute(sa.select(UpcCode.status, sa.func.count()).group_by(UpcCode.status)).all())
    rows = db.execute(
        sa.select(UpcCode).order_by(UpcCode.created_at, UpcCode.code).limit(limit).offset(offset)
    ).scalars().all()
    return {
        "items": [{"id": r.id, "code": r.code, "status": r.status, "release_id": r.release_id} for r in rows],
        "available": counts.get(UpcStatus.available, 0),
        "assigned": counts.get(UpcStatus.assigned, 0),
        "total": sum(counts.values()),
        "limit": limit,
        "offset": offset,
    }


@router.post("/upcs", response_model=UpcAddResult)
def add_upcs(payload: UpcAddIn, db: Session = Depends(get_db)):
    added, rejected, skipped = upc_service.add_upcs(db, payload.codes)
    db.commit()
    return UpcAddResult(added=added, rejected=rejected, skipped=skipped)


@router.post("/upcs/{upc_id}/unassign", status_code=204)
def unassign_upc(upc_id: uuid.UUID, db: Session = Depends(get_db)):
    """Explicitly return a UPC to the available pool (deliberate action, e.g. after a release delete).

    Locks in the same order as assign_upc (Release, then UpcCode) to avoid
    the reverse-order deadlock shape, and revalidates release_id under lock
    since a concurrent assign/unassign can move it between the initial
    unlocked read and the lock being taken.
    """
    upc = db.get(UpcCode, upc_id)
    if upc is None:
        raise HTTPException(status_code=404, detail="UPC not found")
    original_release_id = upc.release_id

    release = None
    if original_release_id is not None:
        release = db.get(Release, original_release_id, with_for_update=True)

    upc = db.get(UpcCode, upc_id, with_for_update=True, populate_existing=True)
    if upc is None or upc.release_id != original_release_id:
        raise HTTPException(status_code=409, detail="UPC changed concurrently — retry")

    if release is not None and release.upc == upc.code:
        release.upc = None
    upc.status = UpcStatus.available
    upc.release_id = None
    upc.assigned_at = None
    db.commit()
