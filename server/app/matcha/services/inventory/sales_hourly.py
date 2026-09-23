"""Hourly POS sales per location and business date (`inventory_sales_hourly`).

Written by the POS sync, read by Schedule Autopilot to shape a day's staffing
curve to when the store actually sells. Deliberately NOT part of the reviewed
sales-import writer: hours carry no SKU, so they need no item mapping, and a
day whose import is still a draft (unmapped items) still has real hours.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from .pos.base import ExternalSalesHour


async def replace_sales_hours(
    conn, *, company_id: UUID, location_id: UUID, business_date: date,
    source: str, connection_id: UUID | None, hours: Sequence[ExternalSalesHour],
) -> int:
    """Replace one location-day's hours with `hours` — whole, never merged.

    A re-sync of the same day is the same finalized orders again; adding them
    would double the day. An empty `hours` leaves the stored day alone: a
    provider that cannot bucket by hour must not erase one that could.
    """
    if not hours:
        return 0
    async with conn.transaction():
        await conn.execute(
            """DELETE FROM inventory_sales_hourly
               WHERE company_id=$1 AND location_id=$2 AND business_date=$3""",
            company_id, location_id, business_date,
        )
        await conn.executemany(
            """INSERT INTO inventory_sales_hourly(
                   company_id, location_id, business_date, hour, gross_sales,
                   order_count, source, connection_id, updated_at
               ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,NOW())""",
            [
                (company_id, location_id, business_date, int(item.hour), item.gross_sales,
                 int(item.order_count), source, connection_id)
                for item in hours
            ],
        )
    return len(hours)
