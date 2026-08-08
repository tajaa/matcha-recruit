import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.oceanlab.models.base import Base, TimestampMixin
from app.oceanlab.models.enums import JobStatus


class Job(Base, TimestampMixin):
    __tablename__ = "oceanlab_jobs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(sa.String, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(JobStatus, native_enum=False, create_constraint=True, name="status"),
        nullable=False,
        default=JobStatus.queued,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
