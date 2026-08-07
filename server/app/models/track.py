import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Track(Base, TimestampMixin):
    __tablename__ = "tracks"
    __table_args__ = (
        sa.UniqueConstraint(
            "release_id",
            "disc_number",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name="uq_tracks_release_disc_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("releases.id", ondelete="CASCADE"), nullable=False
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recordings.id", ondelete="RESTRICT"), nullable=False
    )
    disc_number: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    title_override: Mapped[str | None] = mapped_column(sa.String, nullable=True)
