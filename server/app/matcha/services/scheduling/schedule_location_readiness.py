"""Location prerequisites for publishing and schedule delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.services.compliance_service._industry import _get_company_canonical_industry


@dataclass(frozen=True)
class LocationReadiness:
    ready_to_publish: bool
    missing_fields: tuple[str, ...]
    jurisdiction_id: UUID | None
    timezone: str | None
    industry_code: str | None


def _nonempty(value: Any) -> bool:
    return value is not None and bool(str(value).strip())


def _valid_timezone(value: str | None) -> bool:
    if not _nonempty(value):
        return False
    try:
        ZoneInfo(str(value))
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


async def get_schedule_location_readiness(
    conn,
    company_id: UUID,
    location_id: UUID | None,
) -> LocationReadiness:
    """Return publish readiness without mutating location or jurisdiction data."""

    if location_id is None:
        return LocationReadiness(
            ready_to_publish=False,
            missing_fields=("location_id",),
            jurisdiction_id=None,
            timezone=None,
            industry_code=None,
        )

    row = await conn.fetchrow(
        """
        SELECT id, address, city, state, zipcode, jurisdiction_id, timezone, naics
        FROM business_locations
        WHERE id = $1 AND company_id = $2
        """,
        location_id,
        company_id,
    )
    if not row:
        return LocationReadiness(
            ready_to_publish=False,
            missing_fields=("location_id",),
            jurisdiction_id=None,
            timezone=None,
            industry_code=None,
        )

    canonical_industry = await _get_company_canonical_industry(conn, company_id)
    industry_code = str(row["naics"]).strip() if _nonempty(row["naics"]) else canonical_industry
    missing: list[str] = []
    for field in ("address", "city", "state", "zipcode"):
        if not _nonempty(row[field]):
            missing.append(field)
    if row["jurisdiction_id"] is None:
        missing.append("jurisdiction_id")
    if not _valid_timezone(row["timezone"]):
        missing.append("timezone")
    if not _nonempty(industry_code):
        missing.append("industry")

    return LocationReadiness(
        ready_to_publish=not missing,
        missing_fields=tuple(missing),
        jurisdiction_id=row["jurisdiction_id"],
        timezone=row["timezone"],
        industry_code=industry_code,
    )


async def assert_schedule_location_ready_to_publish(
    conn,
    company_id: UUID,
    location_id: UUID | None,
) -> None:
    """Raise the stable route-facing error used by publication paths."""

    from fastapi import HTTPException

    readiness = await get_schedule_location_readiness(conn, company_id, location_id)
    if readiness.ready_to_publish:
        return
    raise HTTPException(
        status_code=422,
        detail={
            "code": "schedule_location_not_ready",
            "location_id": str(location_id) if location_id else None,
            "missing_fields": list(readiness.missing_fields),
        },
    )
