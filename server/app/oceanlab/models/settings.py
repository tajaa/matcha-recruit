import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.oceanlab.models.base import Base, TimestampMixin
from app.oceanlab.models.enums import CodeSource


class LabelSettings(Base, TimestampMixin):
    """Singleton (id=1) holding the label's answers to the questions every
    release would otherwise ask again. Applied at create time by
    services/defaults.py — see that module for why prefill beats overlay."""

    __tablename__ = "oceanlab_label_settings"
    __table_args__ = (sa.CheckConstraint("id = 1", name="ck_oceanlab_label_settings_singleton"),)

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, default=1)
    default_artist_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_artists.id", ondelete="SET NULL"), nullable=True
    )
    default_contributor_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_contributors.id", ondelete="SET NULL"), nullable=True
    )
    default_genre: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    default_territories: Mapped[str] = mapped_column(sa.String, nullable=False, default="WW")
    c_line_template: Mapped[str] = mapped_column(sa.String, nullable=False, default="{year} {label}")
    p_line_template: Mapped[str] = mapped_column(sa.String, nullable=False, default="{year} {label}")
    isrc_source: Mapped[CodeSource] = mapped_column(
        sa.Enum(CodeSource, native_enum=False, create_constraint=True, name="isrc_source"),
        nullable=False,
        default=CodeSource.distributor,
    )
    upc_source: Mapped[CodeSource] = mapped_column(
        sa.Enum(CodeSource, native_enum=False, create_constraint=True, name="upc_source"),
        nullable=False,
        default=CodeSource.distributor,
    )
