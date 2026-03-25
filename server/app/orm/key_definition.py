"""
ORM models: RegulationKeyDefinition, RegulationKeyDefinitionHistory, RepositoryAlert.

These tables define the canonical key registry, change tracking, and staleness
alerting for the compliance system. Each key definition is the static contract
that all three data pipelines (Claude Code, API fetches, Gemini) write against.

Schema-only — used for migration generation, not runtime queries.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class RegulationKeyDefinition(TimestampMixin, Base):
    """Canonical definition of a regulation key.

    Each row is one policy concept (e.g., 'state_minimum_wage', 'aguinaldo_christmas_bonus').
    Keys are globally unique within a category — the same key can appear in
    jurisdiction_requirements for many jurisdictions, all pointing back to one definition.

    applicable_countries: NULL = universal (applies to all countries).
    '{MX}' = Mexico-only. '{GB}' = UK-only. Filters gap detection and context output.
    """

    __tablename__ = "regulation_key_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    category_slug: Mapped[str] = mapped_column(String(50), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("compliance_categories.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Enforcement
    enforcing_agency: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    authority_source_urls: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True
    )

    # Variance & weight
    state_variance: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="Moderate"
    )
    base_weight: Mapped[Decimal] = mapped_column(
        Numeric(3, 1), nullable=False, server_default="1.0"
    )

    # Applicability scope
    applies_to_levels: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), server_default="'{state,city}'"
    )
    min_employee_threshold: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    applicable_entity_types: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    applicable_industries: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    applicable_countries: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True
    )

    # Staleness SLA
    update_frequency: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    staleness_warning_days: Mapped[Optional[int]] = mapped_column(
        Integer, server_default="90"
    )
    staleness_critical_days: Mapped[Optional[int]] = mapped_column(
        Integer, server_default="180"
    )
    staleness_expired_days: Mapped[Optional[int]] = mapped_column(
        Integer, server_default="365"
    )

    # Grouping
    key_group: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    category: Mapped["ComplianceCategory"] = relationship("ComplianceCategory")

    __table_args__ = (
        UniqueConstraint("category_slug", "key", name="uq_rkd_category_slug_key"),
        Index("idx_rkd_category", "category_slug"),
        Index("idx_rkd_key_group", "key_group"),
    )


class RegulationKeyDefinitionHistory(Base):
    """Tracks changes to key definitions — field-level audit trail."""

    __tablename__ = "regulation_key_definition_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    key_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulation_key_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_changed: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    change_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    key_definition: Mapped["RegulationKeyDefinition"] = relationship(
        "RegulationKeyDefinition"
    )

    __table_args__ = (
        Index(
            "idx_rkdh_key_def",
            "key_definition_id",
            "changed_at",
        ),
    )


class RepositoryAlert(Base):
    """Staleness and coverage alerts for jurisdiction requirements.

    Generated by scanning jobs that check last_verified_at against
    the key definition's staleness SLA. Surfaced in the admin dashboard.
    """

    __tablename__ = "repository_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    alert_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # stale, missing, expiring, new_key
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # warning, critical, expired
    jurisdiction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        nullable=True,
    )
    key_definition_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulation_key_definitions.id", ondelete="CASCADE"),
        nullable=True,
    )
    requirement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdiction_requirements.id", ondelete="SET NULL"),
        nullable=True,
    )
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    regulation_key: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    days_overdue: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open"
    )  # open, acknowledged, resolved
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    jurisdiction: Mapped[Optional["Jurisdiction"]] = relationship("Jurisdiction")
    key_definition: Mapped[Optional["RegulationKeyDefinition"]] = relationship(
        "RegulationKeyDefinition"
    )

    __table_args__ = (
        Index("idx_repo_alerts_status", "status"),
        Index("idx_repo_alerts_jurisdiction", "jurisdiction_id"),
        Index("idx_repo_alerts_severity", "severity"),
        # Dedup: one open alert per jurisdiction + key_definition + type
        Index(
            "idx_repo_alerts_dedup",
            "jurisdiction_id",
            "key_definition_id",
            "alert_type",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )


# Needed for type hints in relationships above
from .jurisdiction import ComplianceCategory, Jurisdiction  # noqa: E402, F401
