import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.models.base import Base, TimestampMixin
from app.models.enums import ArtistRole, ReleaseStatus, ReleaseType


class Release(Base, TimestampMixin):
    __tablename__ = "releases"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(sa.String, nullable=False)
    release_type: Mapped[ReleaseType] = mapped_column(
        sa.Enum(ReleaseType, native_enum=False, create_constraint=True, name="release_type"),
        nullable=False,
    )
    status: Mapped[ReleaseStatus] = mapped_column(
        sa.Enum(ReleaseStatus, native_enum=False, create_constraint=True, name="status"),
        nullable=False,
        default=ReleaseStatus.draft,
    )
    upc: Mapped[str | None] = mapped_column(sa.String(13), unique=True, nullable=True)
    catalog_number: Mapped[str | None] = mapped_column(sa.String, unique=True, nullable=True)
    release_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    original_release_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    label_name: Mapped[str] = mapped_column(sa.String, nullable=False, default=lambda: settings.label_name)
    c_line: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    p_line: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    genre: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    subgenre: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    territories: Mapped[str] = mapped_column(sa.String, nullable=False, default="WW")
    artwork_file_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("files.id", ondelete="RESTRICT"), nullable=True
    )
    primary_artist_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("artists.id"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ReleaseArtist(Base, TimestampMixin):
    __tablename__ = "release_artists"
    __table_args__ = (
        sa.UniqueConstraint("release_id", "artist_id", "role", name="uq_release_artists_release_artist_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("releases.id", ondelete="CASCADE"), nullable=False
    )
    artist_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), sa.ForeignKey("artists.id"), nullable=False)
    role: Mapped[ArtistRole] = mapped_column(
        sa.Enum(ArtistRole, native_enum=False, create_constraint=True, name="role"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
