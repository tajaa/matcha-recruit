import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import UpcStatus


class IsrcConfig(Base, TimestampMixin):
    __tablename__ = "isrc_config"
    __table_args__ = (sa.CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, default=1)
    registrant_prefix: Mapped[str] = mapped_column(sa.String(5), nullable=False, default="")
    year_digits: Mapped[str] = mapped_column(sa.String(2), nullable=False, default="")
    next_designation: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)


class UpcCode(Base, TimestampMixin):
    __tablename__ = "upc_codes"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(sa.String(13), unique=True, nullable=False)
    status: Mapped[UpcStatus] = mapped_column(
        sa.Enum(UpcStatus, native_enum=False, create_constraint=True, name="status"),
        nullable=False,
        default=UpcStatus.available,
    )
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("releases.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
