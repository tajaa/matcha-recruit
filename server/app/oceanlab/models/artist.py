import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.oceanlab.models.base import Base, TimestampMixin


class Artist(Base, TimestampMixin):
    __tablename__ = "oceanlab_artists"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String, unique=True, nullable=False)
    sort_name: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    country: Mapped[str | None] = mapped_column(sa.String(2), nullable=True)
    spotify_id: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    apple_music_id: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
