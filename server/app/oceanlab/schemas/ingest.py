import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.oceanlab.models.enums import JobStatus


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    width: int | None = None
    height: int | None = None
    created_at: datetime
    updated_at: datetime


class AudioUploadRead(BaseModel):
    file: FileRead
    job_id: uuid.UUID


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: JobStatus
    result: dict | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class IssueRead(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str
    field: str | None = None
    track_id: uuid.UUID | None = None


class ValidationRead(BaseModel):
    packageable: bool
    issues: list[IssueRead]


class PackageStartRead(BaseModel):
    delivery_id: uuid.UUID
    job_id: uuid.UUID
