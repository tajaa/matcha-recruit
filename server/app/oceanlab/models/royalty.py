import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.oceanlab.models.base import Base, TimestampMixin
from app.oceanlab.models.enums import MatchMethod, StatementStatus


class RoyaltyStatement(Base, TimestampMixin):
    __tablename__ = "oceanlab_royalty_statements"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(sa.String, nullable=False)
    period_start: Mapped[date] = mapped_column(sa.Date, nullable=False)
    period_end: Mapped[date] = mapped_column(sa.Date, nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_files.id"), nullable=False)
    status: Mapped[StatementStatus] = mapped_column(
        sa.Enum(StatementStatus, native_enum=False, create_constraint=True, name="statement_status"),
        nullable=False,
        default=StatementStatus.uploaded,
    )
    total_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4), nullable=True)
    line_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    matched_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)


class RoyaltyLine(Base, TimestampMixin):
    __tablename__ = "oceanlab_royalty_lines"
    __table_args__ = (
        sa.Index("ix_oceanlab_royalty_lines_statement_id", "statement_id"),
        sa.Index("ix_oceanlab_royalty_lines_isrc", "isrc"),
        sa.Index("ix_oceanlab_royalty_lines_recording_id", "recording_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_royalty_statements.id", ondelete="CASCADE"), nullable=False
    )
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    isrc: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    iswc: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    upc: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    title_raw: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    artist_raw: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    territory: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    units: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_recordings.id", ondelete="SET NULL"), nullable=True
    )
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("oceanlab_works.id", ondelete="SET NULL"), nullable=True
    )
    match_method: Mapped[MatchMethod] = mapped_column(
        sa.Enum(MatchMethod, native_enum=False, create_constraint=True, name="match_method"),
        nullable=False,
        default=MatchMethod.unmatched,
    )
