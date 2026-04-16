#!/usr/bin/env python3
"""Seed BLS OEWS wage benchmarks from the curated QSR subset CSV.

Idempotent — safe to re-run after the source CSV is updated. Uses
ON CONFLICT (soc_code, area_type, area_code, period) DO UPDATE so
the same period overwrites; new periods append.

Usage:
    cd server
    python3 scripts/seed_wage_benchmarks.py

Prereq: alembic upgrade head (so wage_benchmarks table exists).
Source data: server/app/matcha/data/oews_qsr_subset.csv
"""

import asyncio
import csv
import os
import sys
from decimal import Decimal, InvalidOperation

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.database import close_pool, get_connection, init_pool

CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app",
    "matcha",
    "data",
    "oews_qsr_subset.csv",
)


def _decimal(val: str) -> Decimal | None:
    s = (val or "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


async def seed():
    settings = load_settings()
    await init_pool(settings.database_url)

    if not os.path.exists(CSV_PATH):
        print(f"ERROR: source CSV not found at {CSV_PATH}")
        sys.exit(1)

    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} benchmark rows from {os.path.basename(CSV_PATH)}")

    inserted = 0
    updated = 0

    async with get_connection() as conn:
        async with conn.transaction():
            for row in rows:
                # Detect insert vs. update for the progress count
                exists = await conn.fetchval(
                    """
                    SELECT 1 FROM wage_benchmarks
                    WHERE soc_code = $1 AND area_type = $2
                      AND area_code = $3 AND period = $4
                    LIMIT 1
                    """,
                    row["soc_code"], row["area_type"], row["area_code"], row["period"],
                )

                await conn.execute(
                    """
                    INSERT INTO wage_benchmarks
                        (soc_code, soc_label, area_type, area_code, area_name, state,
                         hourly_p10, hourly_p25, hourly_p50, hourly_p75, hourly_p90,
                         annual_p50, source, period, refreshed_at)
                    VALUES
                        ($1, $2, $3, $4, $5, $6,
                         $7, $8, $9, $10, $11,
                         $12, 'BLS_OEWS', $13, NOW())
                    ON CONFLICT (soc_code, area_type, area_code, period) DO UPDATE
                    SET soc_label   = EXCLUDED.soc_label,
                        area_name   = EXCLUDED.area_name,
                        state       = EXCLUDED.state,
                        hourly_p10  = EXCLUDED.hourly_p10,
                        hourly_p25  = EXCLUDED.hourly_p25,
                        hourly_p50  = EXCLUDED.hourly_p50,
                        hourly_p75  = EXCLUDED.hourly_p75,
                        hourly_p90  = EXCLUDED.hourly_p90,
                        annual_p50  = EXCLUDED.annual_p50,
                        refreshed_at = NOW()
                    """,
                    row["soc_code"],
                    row.get("soc_label"),
                    row["area_type"],
                    row["area_code"],
                    row.get("area_name") or None,
                    (row.get("state") or "").upper() or None,
                    _decimal(row.get("hourly_p10", "")),
                    _decimal(row.get("hourly_p25", "")),
                    _decimal(row.get("hourly_p50", "")),
                    _decimal(row.get("hourly_p75", "")),
                    _decimal(row.get("hourly_p90", "")),
                    _decimal(row.get("annual_p50", "")),
                    row["period"],
                )
                if exists:
                    updated += 1
                else:
                    inserted += 1

    total = await _count_rows()
    print(f"Done · inserted {inserted} · updated {updated} · table total {total}")
    await close_pool()


async def _count_rows() -> int:
    async with get_connection() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM wage_benchmarks") or 0


if __name__ == "__main__":
    asyncio.run(seed())
