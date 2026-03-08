#!/usr/bin/env python3
"""Seed zip_county_reference table from the uszipcode package.

Usage:
    pip install uszipcode
    python server/scripts/seed_zip_counties.py

Populates ~42k US zip→county mappings.  Safe to re-run (uses ON CONFLICT).
"""

import asyncio
import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def seed():
    try:
        from uszipcode import SearchEngine
    except ImportError:
        print("Install uszipcode first:  pip install uszipcode")
        sys.exit(1)

    from app.config import load_settings
    from app.database import init_pool, get_pool

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    search = SearchEngine()
    # Fetch all zip codes
    all_zips = search.by_pattern("", returns=50000)
    print(f"Found {len(all_zips)} zip codes in uszipcode database")

    batch = []
    skipped = 0
    for z in all_zips:
        if not z.zipcode or not z.county or not z.state:
            skipped += 1
            continue
        # uszipcode county format: "Example County" — keep as-is
        county = z.county.replace(" County", "").strip() if z.county else None
        if not county:
            skipped += 1
            continue
        batch.append((z.zipcode, county, z.state, z.major_city or ""))

    print(f"Inserting {len(batch)} zip→county mappings (skipped {skipped} incomplete)")

    async with pool.acquire() as conn:
        # Bulk insert in chunks of 1000
        chunk_size = 1000
        inserted = 0
        for i in range(0, len(batch), chunk_size):
            chunk = batch[i : i + chunk_size]
            await conn.executemany(
                """
                INSERT INTO zip_county_reference (zipcode, county, state, city)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (zipcode) DO UPDATE
                    SET county = EXCLUDED.county,
                        state = EXCLUDED.state,
                        city = EXCLUDED.city
                """,
                chunk,
            )
            inserted += len(chunk)
            print(f"  ... {inserted}/{len(batch)}")

    print(f"Done. {inserted} zip codes seeded.")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(seed())
