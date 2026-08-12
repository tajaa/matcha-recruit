import uuid
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.oceanlab.db import get_db
from app.oceanlab.deps import AuthDep
from app.oceanlab.models.delivery import Delivery
from app.oceanlab.models.enums import DeliveryStatus, DeliveryTarget, FileKind
from app.oceanlab.models.file import File
from app.oceanlab.models.job import Job
from app.oceanlab.models.recording import Recording
from app.oceanlab.models.release import Release
from app.oceanlab.routers._errors import OceanlabRoute
from app.oceanlab.schemas.ingest import AudioUploadRead, FileRead, JobRead, PackageStartRead, ValidationRead
from app.oceanlab.services import artwork as artwork_service
from app.oceanlab.services import audio_meta
from app.oceanlab.services import packaging
from app.oceanlab.services import validation
from app.oceanlab.services.jobs import create_job, register, run_job
from app.oceanlab.services.storage import artwork_key, get_store, master_key


router = APIRouter(route_class=OceanlabRoute, tags=["ingestion"], dependencies=[AuthDep])


def _safe_filename(upload: UploadFile, fallback: str) -> str:
    return Path(upload.filename or fallback).name


@register("extract_audio_meta")
def _extract_audio_meta(db: Session, payload: dict) -> dict:
    recording = db.get(Recording, uuid.UUID(payload["recording_id"]))
    if not recording:
        raise ValueError("Recording not found")
    store = get_store()
    with store.local_copy(payload["storage_key"]) as path:
        meta = audio_meta.extract(path)
    recording.duration_seconds = meta.duration_seconds
    recording.sample_rate = meta.sample_rate
    recording.bit_depth = meta.bit_depth
    recording.channels = meta.channels
    recording.audio_format = meta.audio_format
    db.commit()
    return {"duration_seconds": str(meta.duration_seconds), "sample_rate": meta.sample_rate, "bit_depth": meta.bit_depth, "channels": meta.channels, "audio_format": meta.audio_format}


@register("build_package")
def _build_package(db: Session, payload: dict) -> dict:
    result = packaging.build_package(db, uuid.UUID(payload["release_id"]), uuid.UUID(payload["delivery_id"]))
    return {"file_id": str(result.file_id), "manifest_rows": result.manifest_rows, "total_bytes": result.total_bytes}


@router.post("/recordings/{recording_id}/audio", response_model=AudioUploadRead)
def upload_audio(recording_id: uuid.UUID, file: UploadFile = FastAPIFile(...), db: Session = Depends(get_db)):
    recording = db.get(Recording, recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    filename = _safe_filename(file, "master.wav")
    ext = Path(filename).suffix.lower()
    if ext not in {".wav", ".flac"}:
        raise HTTPException(status_code=422, detail="Master filename must end in .wav or .flac")
    key = master_key(recording_id, ext)
    store = get_store()
    try:
        # Probe before touching the deterministic storage key. A failed retry
        # must not remove the last known-good master at that key.
        with tempfile.NamedTemporaryFile(suffix=ext) as probe:
            shutil.copyfileobj(file.file, probe)
            probe.flush()
            probe.seek(0)
            audio_meta.extract(Path(probe.name))
            probe.seek(0)
            size, sha = store.put(key, probe, content_type=file.content_type or "application/octet-stream")
    except Exception as exc:
        if isinstance(exc, audio_meta.AudioMetaError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise HTTPException(status_code=503, detail=f"Master upload failed: {exc}") from exc
    previous = db.get(File, recording.audio_file_id) if recording.audio_file_id else None
    file_row = previous or File(kind=FileKind.audio_master, storage_key=key, original_filename=filename, mime_type=file.content_type or "application/octet-stream", size_bytes=size, sha256=sha)
    file_row.kind = FileKind.audio_master
    file_row.storage_key = key
    file_row.original_filename = filename
    file_row.mime_type = file.content_type or "application/octet-stream"
    file_row.size_bytes = size
    file_row.sha256 = sha
    db.add(file_row)
    db.flush()
    recording.audio_file_id = file_row.id
    job = create_job(db, "extract_audio_meta", {"recording_id": str(recording_id), "storage_key": key})
    db.commit()
    run_job(db, db.get(Job, job.id))
    db.refresh(file_row)
    return {"file": file_row, "job_id": job.id}


@router.post("/releases/{release_id}/artwork", response_model=FileRead)
def upload_artwork(release_id: uuid.UUID, file: UploadFile = FastAPIFile(...), db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    data = file.file.read()
    try:
        meta = artwork_service.validate_artwork(data)
    except artwork_service.ArtworkError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ext = ".jpg" if meta.format == "jpeg" else ".png"
    key = artwork_key(release_id, ext)
    import io
    store = get_store()
    size, sha = store.put(key, io.BytesIO(data), content_type=file.content_type or f"image/{meta.format}")
    previous = db.get(File, release.artwork_file_id) if release.artwork_file_id else None
    file_row = previous or File(kind=FileKind.artwork, storage_key=key, original_filename=_safe_filename(file, f"cover{ext}"), mime_type=file.content_type or f"image/{meta.format}", size_bytes=size, sha256=sha, width=meta.width, height=meta.height)
    file_row.kind = FileKind.artwork
    file_row.storage_key = key
    file_row.original_filename = _safe_filename(file, f"cover{ext}")
    file_row.mime_type = file.content_type or f"image/{meta.format}"
    file_row.size_bytes = size
    file_row.sha256 = sha
    file_row.width = meta.width
    file_row.height = meta.height
    db.add(file_row)
    db.flush()
    release.artwork_file_id = file_row.id
    db.commit()
    db.refresh(file_row)
    return file_row


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/releases/{release_id}/validation", response_model=ValidationRead)
def get_validation(release_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        report = validation.validate_release(db, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"packageable": report.packageable, "issues": report.issues}


@router.post("/releases/{release_id}/ready", response_model=ValidationRead)
def mark_ready(release_id: uuid.UUID, db: Session = Depends(get_db)):
    report = validation.validate_release(db, release_id)
    if not report.packageable:
        raise HTTPException(status_code=409, detail={"message": "Release is not ready", "issues": [issue.__dict__ for issue in report.issues]})
    release = db.get(Release, release_id)
    release.status = "ready"
    db.commit()
    return {"packageable": True, "issues": report.issues}


@router.post("/releases/{release_id}/package", response_model=PackageStartRead)
def start_package(release_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(Release, release_id) is None:
        raise HTTPException(status_code=404, detail="Release not found")
    report = validation.validate_release(db, release_id)
    if not report.packageable:
        raise HTTPException(status_code=409, detail={"message": "Release cannot be packaged", "issues": [issue.__dict__ for issue in report.issues]})
    delivery = Delivery(release_id=release_id, target=DeliveryTarget.export_package, status=DeliveryStatus.pending)
    db.add(delivery)
    db.flush()
    job = create_job(db, "build_package", {"release_id": str(release_id), "delivery_id": str(delivery.id)})
    db.commit()
    run_job(db, db.get(Job, job.id))
    return {"delivery_id": delivery.id, "job_id": job.id}


@router.get("/deliveries/{delivery_id}/download")
def download_package(delivery_id: uuid.UUID, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse, StreamingResponse
    delivery = db.get(Delivery, delivery_id)
    if not delivery or delivery.target != DeliveryTarget.export_package or not delivery.package_file_id:
        raise HTTPException(status_code=404, detail="Package not found")
    file_row = db.get(File, delivery.package_file_id)
    url = get_store().presigned_url(file_row.storage_key)
    if url:
        return RedirectResponse(url)
    source = get_store().open(file_row.storage_key)
    return StreamingResponse(source, media_type=file_row.mime_type, headers={"Content-Disposition": f'attachment; filename="{file_row.original_filename}"'})
