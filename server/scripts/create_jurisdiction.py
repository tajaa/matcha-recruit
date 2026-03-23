#!/usr/bin/env python3
"""
Create a jurisdiction row in the database (no compliance research).

Usage:
    python scripts/create_jurisdiction.py "Indianapolis" "IN"
    python scripts/create_jurisdiction.py "Indianapolis" "IN" --county "Marion"
    python scripts/create_jurisdiction.py "Indianapolis" "IN" --dry-run

Prints the jurisdiction ID on success. Use with /research-jurisdiction skill
which handles compliance research via Claude Code.
"""

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SKIP_REDIS", "1")

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


async def main():
    parser = argparse.ArgumentParser(description="Create a jurisdiction row")
    parser.add_argument("city", help="City name")
    parser.add_argument("state", help="Two-letter state code")
    parser.add_argument("--county", help="County name")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually insert")
    args = parser.parse_args()

    city = args.city.strip().title()
    state = args.state.strip().upper()
    county = args.county.strip().title() if args.county else None

    if state not in US_STATE_CODES:
        print(f"ERROR: '{state}' is not a valid US state code.")
        sys.exit(1)

    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, city, state, county FROM jurisdictions "
                "WHERE LOWER(city) = LOWER($1) AND state = $2",
                city, state,
            )
            if existing:
                print(f"EXISTING:{existing['id']}:{existing['city']}:{existing['state']}:{existing['county'] or ''}")
                return

            jurisdiction_id = uuid.uuid4()
            display_name = f"{city}, {state}"

            if args.dry_run:
                print(f"DRY_RUN:{jurisdiction_id}:{city}:{state}:{county or ''}")
            else:
                await conn.execute(
                    """
                    INSERT INTO jurisdictions (id, city, state, county, display_name, level, authority_type)
                    VALUES ($1, $2, $3, $4, $5, 'city', 'geographic')
                    """,
                    jurisdiction_id, city, state, county, display_name,
                )
                print(f"CREATED:{jurisdiction_id}:{city}:{state}:{county or ''}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
