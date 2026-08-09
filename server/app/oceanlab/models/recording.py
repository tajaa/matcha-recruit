import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.oceanlab.models.base import Base, TimestampMixin
from app.oceanlab.models.enums import CreditRole


class Recording(Base, TimestampMixin):
    __tablename__ = "oceanlab_recordings"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(sa.String, nullable=False)
    version: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    isrc: Mapped[str | None] = mapped_column(sa.String(12), unique=True, nullable=True)
    explicit: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    language: Mapped[str | None] = mapped_column(sa.String(2), nullable=True)
    recording_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    audio_file_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("oceanlab_files.id", ondelete="RESTRICT"),
        nullable=True,
    )
    duration_seconds: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(9, 3), nullable=True
    )
    sample_rate: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    bit_depth: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    audio_format: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    primary_artist_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_artists.id"), nullable=False
    )


class Credit(Base, TimestampMixin):
    __tablename__ = "oceanlab_credits"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("oceanlab_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    contributor_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_contributors.id"), nullable=False
    )
    role: Mapped[CreditRole] = mapped_column(
        sa.Enum(CreditRole, native_enum=False, create_constraint=True, name="role"),
        nullable=False,
    )
    credited_as: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class MasterSplit(Base, TimestampMixin):
    __tablename__ = "oceanlab_master_splits"
    __table_args__ = (
        sa.UniqueConstraint(
            "recording_id",
            "contributor_id",
            name="uq_oceanlab_master_splits_recording_contributor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("oceanlab_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    contributor_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_contributors.id"), nullable=False
    )
    role: Mapped[CreditRole | None] = mapped_column(
        sa.Enum(CreditRole, native_enum=False, create_constraint=True, name="role"),
        nullable=True,
    )
    share_pct: Mapped[Decimal] = mapped_column(sa.Numeric(6, 3), nullable=False)
    auto_created: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
