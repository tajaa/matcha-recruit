"""Persistence and refresh helpers for daily Schedule Autopilot weather."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.core.services.geo import geocode
from app.core.services.weather.google_weather import fetch_daily_forecast

logger = logging.getLogger(__name__)


async def upsert_weather_days(
    conn, *, company_id: UUID, location_id: UUID, rows: list[dict], today: date,
) -> int:
    written = 0
    for row in rows:
        local_date = row.get("local_date")
        if not isinstance(local_date, date) or local_date < today:
            continue
        result = await conn.execute(
            """
            INSERT INTO schedule_weather_days(
                company_id, location_id, local_date, condition, precip_probability,
                precip_qpf_mm, max_temp_c, min_temp_c, provider, fetched_at, raw
            ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,'google',NOW(),$9::jsonb)
            ON CONFLICT (location_id, local_date) DO UPDATE SET
                company_id=EXCLUDED.company_id,
                condition=EXCLUDED.condition,
                precip_probability=EXCLUDED.precip_probability,
                precip_qpf_mm=EXCLUDED.precip_qpf_mm,
                max_temp_c=EXCLUDED.max_temp_c,
                min_temp_c=EXCLUDED.min_temp_c,
                provider=EXCLUDED.provider,
                fetched_at=NOW(),
                raw=EXCLUDED.raw
            WHERE EXCLUDED.local_date >= $10
            """,
            company_id, location_id, local_date, row.get("condition"),
            row.get("precip_probability"), row.get("precip_qpf_mm"),
            row.get("max_temp_c"), row.get("min_temp_c"),
            json.dumps(row.get("raw") or {}, default=str), today,
        )
        if result != "INSERT 0 0":
            written += 1
    return written


async def load_weather_days(
    conn, *, company_id: UUID, location_id: UUID, start: date, end: date,
) -> dict[date, dict]:
    rows = await conn.fetch(
        """
        SELECT local_date, condition, precip_probability, precip_qpf_mm,
               max_temp_c, min_temp_c, fetched_at
        FROM schedule_weather_days
        WHERE company_id=$1 AND location_id=$2 AND local_date BETWEEN $3 AND $4
        ORDER BY local_date
        """,
        company_id, location_id, start, end,
    )
    return {
        row["local_date"]: {
            "condition": row["condition"],
            "precip_probability": row["precip_probability"],
            "precip_qpf_mm": row["precip_qpf_mm"],
            "max_temp_c": row["max_temp_c"],
            "min_temp_c": row["min_temp_c"],
            "fetched_at": row["fetched_at"],
        }
        for row in rows
    }


async def ensure_location_coordinates(
    conn, client: httpx.AsyncClient, *, company_id: UUID, location_id: UUID,
) -> tuple[float, float] | None:
    try:
        row = await conn.fetchrow(
            """SELECT lat, lng, address, city, state, zipcode, country_code
               FROM business_locations WHERE id=$1 AND company_id=$2""",
            location_id, company_id,
        )
        if not row:
            return None
        if row["lat"] is not None and row["lng"] is not None:
            return float(row["lat"]), float(row["lng"])
        if row.get("country_code") not in (None, "", "US", "USA"):
            return None
        result = await geocode(client, row["address"], row["city"], row["state"], row["zipcode"])
        if not result:
            return None
        lat, lng = float(result["lat"]), float(result["lng"])
        await conn.execute(
            """UPDATE business_locations
               SET lat=$1, lng=$2, geocoded_at=NOW(), geocode_source=$3
               WHERE id=$4 AND company_id=$5""",
            lat, lng, result.get("source") or "census", location_id, company_id,
        )
        return lat, lng
    except Exception:
        logger.warning("Autopilot coordinate lookup failed for %s", location_id, exc_info=True)
        return None


async def refresh_location_weather(
    conn, *, company_id: UUID, location_id: UUID,
) -> dict[date, dict]:
    location = await conn.fetchrow(
        "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
        location_id, company_id,
    )
    if not location or not location["timezone"]:
        return {}
    try:
        today = datetime.now(ZoneInfo(location["timezone"])).date()
    except (KeyError, ValueError, ZoneInfoNotFoundError):
        return {}
    async with httpx.AsyncClient(follow_redirects=True) as client:
        coords = await ensure_location_coordinates(
            conn, client, company_id=company_id, location_id=location_id,
        )
    if not coords:
        return {}
    rows = await fetch_daily_forecast(lat=coords[0], lng=coords[1], days=10)
    if rows is None:
        return {}
    await upsert_weather_days(
        conn, company_id=company_id, location_id=location_id, rows=rows, today=today,
    )
    return await load_weather_days(
        conn, company_id=company_id, location_id=location_id,
        start=today, end=today + timedelta(days=9),
    )
