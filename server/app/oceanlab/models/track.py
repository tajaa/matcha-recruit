import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.oceanlab.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.oceanlab.models.recording import Recording


class Track(Base, TimestampMixin):
    __tablename__ = "oceanlab_tracks"
    __table_args__ = (
        # INITIALLY DEFERRED so reorder_tracks can renumber a whole disc's
        # positions within one transaction without hitting a transient
        # duplicate on the (release_id, disc_number, position) tuple.
        sa.UniqueConstraint(
            "release_id",
            "disc_number",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name="uq_oceanlab_tracks_release_disc_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_releases.id", ondelete="CASCADE"), nullable=False
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_recordings.id", ondelete="RESTRICT"), nullable=False
    )
    disc_number: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    title_override: Mapped[str | None] = mapped_column(sa.String, nullable=True)

    recording: Mapped["Recording"] = relationship(lazy="joined")
