"""
ORM models: JurisdictionRequirement, PolicyChangeLog.

Each JurisdictionRequirement row is one policy — a statute, ordinance,
regulation, or rule. Categories group policies, but the policy is the
atomic unit with its own canonical_key, fetch_hash, status lifecycle,
and legal citation.
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
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import ChangeSource, RequirementStatus, SourceTier


class JurisdictionRequirement(TimestampMixin, Base):
    __tablename__ = "jurisdiction_requirements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_key: Mapped[str] = mapped_column(Text, nullable=False)
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
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    is_bookmarked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    rate_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    requires_written_policy: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )
    applicable_industries: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True
    )
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # --- NEW columns (added in Migration 4) ---
    canonical_key: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("compliance_categories.id"),
        nullable=True,  # NOT NULL enforced after backfill in migration
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    full_text_reference: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    statute_citation: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    fetch_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    status: Mapped[RequirementStatus] = mapped_column(
        nullable=False, server_default="active"
    )
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdiction_requirements.id"),
        nullable=True,
    )
    applicable_entity_types: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    trigger_conditions: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    metadata_extra: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    source_tier: Mapped[Optional[SourceTier]] = mapped_column(nullable=True)

    # Relationships
    jurisdiction: Mapped["Jurisdiction"] = relationship(
        "Jurisdiction", back_populates="requirements"
    )
    category_ref: Mapped[Optional["ComplianceCategory"]] = relationship(
        "ComplianceCategory"
    )
    superseded_by: Mapped[Optional["JurisdictionRequirement"]] = relationship(
        "JurisdictionRequirement", remote_side="JurisdictionRequirement.id"
    )

    __table_args__ = (
        Index("ix_jurisdiction_requirements_jurisdiction_id", "jurisdiction_id"),
        Index("ix_jurisdiction_requirements_category_id", "category_id"),
        Index("ix_jurisdiction_requirements_status", "status"),
        Index("ix_jurisdiction_requirements_canonical_key", "canonical_key"),
        Index("ix_jurisdiction_requirements_source_tier", "source_tier"),
    )


class PolicyChangeLog(Base):
    __tablename__ = "policy_change_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdiction_requirements.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_changed: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    change_source: Mapped[ChangeSource] = mapped_column(nullable=False)
    change_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    requirement: Mapped["JurisdictionRequirement"] = relationship(
        "JurisdictionRequirement"
    )

    __table_args__ = (
        Index("ix_policy_change_log_requirement_id", "requirement_id"),
        Index("ix_policy_change_log_changed_at", "changed_at"),
    )


# Needed for type hints in jurisdiction.py relationship
from .jurisdiction import ComplianceCategory, Jurisdiction  # noqa: E402, F401
