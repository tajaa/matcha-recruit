import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import JobStatus


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: JobStatus
    payload: dict
    result: dict | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
