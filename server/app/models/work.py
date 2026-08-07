import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import WriterRole


class Work(Base, TimestampMixin):
    __tablename__ = "works"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(sa.String, nullable=False)
    iswc: Mapped[str | None] = mapped_column(sa.String(11), unique=True, nullable=True)
    language: Mapped[str | None] = mapped_column(sa.String(2), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class RecordingWork(Base):
    __tablename__ = "recording_works"

    recording_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recordings.id", ondelete="CASCADE"), primary_key=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("works.id", ondelete="CASCADE"), primary_key=True
    )


class WorkWriter(Base, TimestampMixin):
    __tablename__ = "work_writers"
    __table_args__ = (
        sa.UniqueConstraint("work_id", "contributor_id", "role", name="uq_work_writers_work_contributor_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("works.id", ondelete="CASCADE"), nullable=False
    )
    contributor_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("contributors.id"), nullable=False
    )
    role: Mapped[WriterRole] = mapped_column(sa.Enum(WriterRole, native_enum=False), nullable=False)
    share_pct: Mapped[Decimal] = mapped_column(sa.Numeric(6, 3), nullable=False)
    publisher_name: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    publisher_share_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 3), nullable=True)
