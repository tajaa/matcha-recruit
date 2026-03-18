"""
ORM model: EmployeeJurisdiction — maps employees to jurisdictions.

Supports multiple relationship types: licensed_in, works_at,
telehealth_coverage, historical. RLS policy defined in Migration 5.
"""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .enums import EmployeeJurisdictionRelType


class EmployeeJurisdiction(Base):
    __tablename__ = "employee_jurisdictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[EmployeeJurisdictionRelType] = mapped_column(
        nullable=False
    )
    effective_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True
    )
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "jurisdiction_id",
            "relationship_type",
            name="uq_employee_jurisdictions_emp_jur_rel",
        ),
        Index("ix_employee_jurisdictions_employee_id", "employee_id"),
        Index("ix_employee_jurisdictions_jurisdiction_id", "jurisdiction_id"),
        Index(
            "ix_employee_jurisdictions_relationship_type", "relationship_type"
        ),
    )
