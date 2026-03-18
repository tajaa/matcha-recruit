"""
ORM model: ComplianceRequirement — per-location compliance data.

Mirrors the existing compliance_requirements table + 3 new explainability
columns for governance tracking.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ComplianceRequirement(TimestampMixin, Base):
    __tablename__ = "compliance_requirements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    jurisdiction_level: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    jurisdiction_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_value: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    numeric_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4), nullable=True
    )
    source_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    source_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    effective_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True
    )
    expiration_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True
    )
    previous_value: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    last_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    requirement_key: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    rate_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    applicable_industries: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True
    )
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # --- NEW explainability columns (added in Migration 5) ---
    governing_jurisdiction_level: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    governing_precedence_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("precedence_rules.id"),
        nullable=True,
    )
    governance_source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="not_evaluated"
    )

    # Relationships
    location: Mapped["BusinessLocation"] = relationship("BusinessLocation")
    governing_rule: Mapped[Optional["PrecedenceRule"]] = relationship(
        "PrecedenceRule"
    )

    __table_args__ = (
        Index("ix_compliance_requirements_location_id", "location_id"),
        Index("ix_compliance_requirements_category", "category"),
    )


from .jurisdiction import PrecedenceRule  # noqa: E402, F401
from .location import BusinessLocation  # noqa: E402, F401
