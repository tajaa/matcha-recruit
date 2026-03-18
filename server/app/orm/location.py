"""
ORM model: BusinessLocation — schema-only mirror of existing table.

Mirrors the existing business_locations table so other ORM models can
declare FK relationships to it. No new columns except facility_attributes.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class BusinessLocation(TimestampMixin, Base):
    __tablename__ = "business_locations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    county: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    zipcode: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default="true"
    )
    last_compliance_check: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    auto_check_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="true"
    )
    auto_check_interval_days: Mapped[int] = mapped_column(
        Integer, server_default="7"
    )
    next_auto_check: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(
        String(20), server_default="manual"
    )
    coverage_status: Mapped[Optional[str]] = mapped_column(
        String(20), server_default="covered"
    )
    jurisdiction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id"),
        nullable=True,
    )
    # NEW: structured facility attributes for trigger condition evaluation
    facility_attributes: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
