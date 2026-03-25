"""
ORM models: Jurisdiction, ComplianceCategory, PrecedenceRule.

Schema-only — used for migration generation, not runtime queries.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import (
    CategoryDomain,
    JurisdictionLevel,
    PrecedenceRuleStatus,
    PrecedenceType,
)


class Jurisdiction(TimestampMixin, Base):
    __tablename__ = "jurisdictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    county: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[JurisdictionLevel] = mapped_column(
        nullable=False, server_default="city"
    )
    country_code: Mapped[str] = mapped_column(
        String(2), nullable=False, server_default="US"
    )
    authority_type: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="geographic"
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    requirement_count: Mapped[int] = mapped_column(
        Integer, server_default="0"
    )
    legislation_count: Mapped[int] = mapped_column(
        Integer, server_default="0"
    )

    # Relationships (schema-only, not used at runtime)
    parent: Mapped[Optional["Jurisdiction"]] = relationship(
        "Jurisdiction", remote_side="Jurisdiction.id", back_populates="children"
    )
    children: Mapped[List["Jurisdiction"]] = relationship(
        "Jurisdiction", back_populates="parent"
    )
    requirements: Mapped[List["JurisdictionRequirement"]] = relationship(
        "JurisdictionRequirement", back_populates="jurisdiction"
    )

    __table_args__ = (
        Index("ix_jurisdictions_level", "level"),
        Index("ix_jurisdictions_parent_id", "parent_id"),
        Index("ix_jurisdictions_state", "state"),
        Index("ix_jurisdictions_authority_type", "authority_type"),
    )


# Import here to avoid circular — JurisdictionRequirement is in requirement.py
# but we need it for the relationship type hint above.
# SQLAlchemy resolves string references lazily, so this is safe.


class ComplianceCategory(TimestampMixin, Base):
    __tablename__ = "compliance_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    slug: Mapped[str] = mapped_column(
        String(60), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("compliance_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    domain: Mapped[CategoryDomain] = mapped_column(nullable=False)
    group: Mapped[str] = mapped_column(String(30), nullable=False)
    industry_tag: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True
    )
    research_mode: Mapped[str] = mapped_column(
        String(30), server_default="default_sweep"
    )
    docx_section: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")

    # Relationships
    parent_category: Mapped[Optional["ComplianceCategory"]] = relationship(
        "ComplianceCategory", remote_side="ComplianceCategory.id"
    )

    __table_args__ = (
        Index("ix_compliance_categories_domain", "domain"),
        Index("ix_compliance_categories_group", "group"),
    )


class PrecedenceRule(TimestampMixin, Base):
    __tablename__ = "precedence_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("compliance_categories.id"),
        nullable=False,
    )
    higher_jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id"),
        nullable=False,
    )
    lower_jurisdiction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id"),
        nullable=True,
    )
    applies_to_all_children: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    precedence_type: Mapped[PrecedenceType] = mapped_column(nullable=False)
    trigger_condition: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    reasoning_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    legal_citation: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    effective_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True
    )
    sunset_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    status: Mapped[PrecedenceRuleStatus] = mapped_column(
        nullable=False, server_default="active"
    )

    # Relationships
    category: Mapped["ComplianceCategory"] = relationship("ComplianceCategory")
    higher_jurisdiction: Mapped["Jurisdiction"] = relationship(
        "Jurisdiction", foreign_keys=[higher_jurisdiction_id]
    )
    lower_jurisdiction: Mapped[Optional["Jurisdiction"]] = relationship(
        "Jurisdiction", foreign_keys=[lower_jurisdiction_id]
    )

    __table_args__ = (
        CheckConstraint(
            "(applies_to_all_children = true AND lower_jurisdiction_id IS NULL) "
            "OR (applies_to_all_children = false AND lower_jurisdiction_id IS NOT NULL)",
            name="ck_precedence_rules_children_xor_lower",
        ),
        Index("ix_precedence_rules_category_id", "category_id"),
        Index("ix_precedence_rules_status", "status"),
        Index(
            "ix_precedence_rules_lower_jurisdiction_id", "lower_jurisdiction_id"
        ),
        Index(
            "ix_precedence_rules_higher_jurisdiction_id",
            "higher_jurisdiction_id",
        ),
    )
