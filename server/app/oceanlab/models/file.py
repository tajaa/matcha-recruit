import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import FileKind


class File(Base, TimestampMixin):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[FileKind] = mapped_column(
        sa.Enum(FileKind, native_enum=False, create_constraint=True, name="kind"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(sa.String, unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(sa.String, nullable=False)
    mime_type: Mapped[str] = mapped_column(sa.String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
