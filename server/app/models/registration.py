import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import RegStatus, RegTarget


class RegistrationTask(Base, TimestampMixin):
    __tablename__ = "registration_tasks"
    __table_args__ = (
        sa.UniqueConstraint("release_id", "target", name="uq_registration_tasks_release_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("releases.id", ondelete="CASCADE"), nullable=False
    )
    target: Mapped[RegTarget] = mapped_column(sa.Enum(RegTarget, native_enum=False), nullable=False)
    status: Mapped[RegStatus] = mapped_column(
        sa.Enum(RegStatus, native_enum=False), nullable=False, default=RegStatus.not_started
    )
    external_ref: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    export_file_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("files.id"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
