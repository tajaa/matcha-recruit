import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import DeliveryStatus, DeliveryTarget


class Delivery(Base, TimestampMixin):
    __tablename__ = "deliveries"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("releases.id", ondelete="CASCADE"), nullable=False
    )
    target: Mapped[DeliveryTarget] = mapped_column(
        sa.Enum(DeliveryTarget, native_enum=False, create_constraint=True, name="target"),
        nullable=False,
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        sa.Enum(DeliveryStatus, native_enum=False, create_constraint=True, name="status"),
        nullable=False,
        default=DeliveryStatus.pending,
    )
    package_file_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("files.id"), nullable=True
    )
    external_ref: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    log: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class DeliveryItem(Base, TimestampMixin):
    __tablename__ = "delivery_items"
    __table_args__ = (
        sa.UniqueConstraint("delivery_id", "track_id", name="uq_delivery_items_delivery_track"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        sa.Enum(DeliveryStatus, native_enum=False, create_constraint=True, name="status"),
        nullable=False,
        default=DeliveryStatus.pending,
    )
    external_ref: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
