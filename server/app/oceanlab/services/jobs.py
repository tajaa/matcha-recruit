"""Small durable job registry used by ingestion and export operations."""

from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.oceanlab.models.enums import JobStatus
from app.oceanlab.models.job import Job


JobHandler = Callable[[Session, dict], dict]
JOB_HANDLERS: dict[str, JobHandler] = {}


def register(kind: str):
    def decorator(handler: JobHandler) -> JobHandler:
        JOB_HANDLERS[kind] = handler
        return handler

    return decorator


def create_job(db: Session, kind: str, payload: dict) -> Job:
    job = Job(kind=kind, payload=payload, status=JobStatus.queued)
    db.add(job)
    db.flush()
    return job


def run_job(db: Session, job: Job) -> Job:
    job.status = JobStatus.running
    job.started_at = datetime.now(timezone.utc)
    handler = JOB_HANDLERS.get(job.kind)
    if handler is None:
        job.status = JobStatus.failed
        job.error = f"Unknown Oceanlab job: {job.kind}"
    else:
        try:
            job.result = handler(db, job.payload)
            job.status = JobStatus.done
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job.id)
            job.status = JobStatus.failed
            job.error = str(exc)
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def sweep_stale(db: Session) -> int:
    result = db.execute(
        sa.update(Job)
        .where(Job.status == JobStatus.running)
        .values(status=JobStatus.failed, error="server restarted", finished_at=datetime.now(timezone.utc))
    )
    db.commit()
    return result.rowcount
