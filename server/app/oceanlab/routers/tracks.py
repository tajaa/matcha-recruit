import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.oceanlab.routers._errors import OceanlabRoute
from app.oceanlab.db import get_db
from app.oceanlab.deps import AuthDep
from app.oceanlab.models.recording import Recording
from app.oceanlab.models.release import Release
from app.oceanlab.models.track import Track
from app.oceanlab.schemas.track import TrackCreate, TrackRead, TrackReadWithRecording, TrackReorder, TrackUpdate

router = APIRouter(route_class=OceanlabRoute, tags=["tracks"], dependencies=[AuthDep])


@router.get("/releases/{release_id}/tracks", response_model=list[TrackReadWithRecording])
def list_tracks(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    tracks = db.execute(
        sa.select(Track)
        .where(Track.release_id == release_id)
        .order_by(Track.disc_number, Track.position)
    ).scalars().all()
    return tracks


@router.post("/releases/{release_id}/tracks", response_model=TrackRead, status_code=201)
def add_track(release_id: uuid.UUID, payload: TrackCreate, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    if db.get(Recording, payload.recording_id) is None:
        raise HTTPException(status_code=404, detail="Recording not found")

    disc_number = payload.disc_number
    position = payload.position
    if position is None:
        current_max = db.execute(
            sa.select(sa.func.max(Track.position)).where(
                Track.release_id == release_id, Track.disc_number == disc_number
            )
        ).scalar_one()
        position = (current_max or 0) + 1

    track = Track(release_id=release_id, recording_id=payload.recording_id, disc_number=disc_number, position=position)
    db.add(track)
    db.commit()
    db.refresh(track)
    return track


@router.post("/releases/{release_id}/tracks/reorder", response_model=list[TrackRead])
def reorder_tracks(release_id: uuid.UUID, payload: TrackReorder, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    tracks = db.execute(
        sa.select(Track).where(Track.release_id == release_id, Track.disc_number == payload.disc_number)
    ).scalars().all()
    by_id = {t.id: t for t in tracks}

    unknown = [str(tid) for tid in payload.track_ids if tid not in by_id]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown track ids (not tracks of this release/disc): {unknown}",
        )

    missing_from_payload = [str(tid) for tid in by_id if tid not in set(payload.track_ids)]
    if missing_from_payload:
        raise HTTPException(
            status_code=422,
            detail=f"Reorder must include the complete set of tracks for this disc; missing: {missing_from_payload}",
        )

    for i, track_id in enumerate(payload.track_ids, start=1):
        by_id[track_id].position = i
    db.commit()

    rows = db.execute(
        sa.select(Track).where(Track.release_id == release_id).order_by(Track.disc_number, Track.position)
    ).scalars().all()
    return rows


@router.patch("/tracks/{track_id}", response_model=TrackRead)
def update_track(track_id: uuid.UUID, payload: TrackUpdate, db: Session = Depends(get_db)):
    track = db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Track not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(track, k, v)
    db.commit()
    db.refresh(track)
    return track


@router.delete("/tracks/{track_id}", status_code=204)
def delete_track(track_id: uuid.UUID, db: Session = Depends(get_db)):
    track = db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Track not found")
    db.delete(track)
    db.commit()
