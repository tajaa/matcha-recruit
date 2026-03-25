#!/usr/bin/env python3
"""
Create a jurisdiction row in the database (no compliance research).

Usage:
    python scripts/create_jurisdiction.py "Indianapolis" "IN"
    python scripts/create_jurisdiction.py "Indianapolis" "IN" --county "Marion"
    python scripts/create_jurisdiction.py "Singapore" --country SG
    python scripts/create_jurisdiction.py "Mexico City" "CDMX" --country MX
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
    parser.add_argument("state", nargs="?", default=None, help="State/province code (optional for city-states)")
    parser.add_argument("--county", help="County name")
    parser.add_argument("--country", default="US", help="ISO 3166-1 alpha-2 country code (default: US)")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually insert")
    args = parser.parse_args()

    city = args.city.strip().title()
    state = args.state.strip().upper() if args.state else None
    county = args.county.strip().title() if args.county else None
    country = args.country.strip().upper()

    if len(country) != 2:
        print(f"ERROR: Country code must be 2 letters (ISO 3166-1), got '{country}'.")
        sys.exit(1)

    # Validate state only for US jurisdictions
    if country == "US":
        if not state:
            print("ERROR: US jurisdictions require a state code.")
            sys.exit(1)
        if state not in US_STATE_CODES:
            print(f"ERROR: '{state}' is not a valid US state code.")
            sys.exit(1)

    # Determine jurisdiction level and display name
    if country == "US":
        level = "city"
        display_name = f"{city}, {state}"
    else:
        level = "city"
        if state:
            display_name = f"{city}, {state}, {country}"
        else:
            display_name = f"{city}, {country}"

    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, city, state, county FROM jurisdictions "
                "WHERE LOWER(city) = LOWER($1) AND COALESCE(state, '') = COALESCE($2, '') AND country_code = $3",
                city, state or '', country,
            )
            if existing:
                print(f"EXISTING:{existing['id']}:{existing['city']}:{existing['state'] or ''}:{existing['county'] or ''}")
                return

            jurisdiction_id = uuid.uuid4()

            if args.dry_run:
                print(f"DRY_RUN:{jurisdiction_id}:{city}:{state or ''}:{county or ''}:{country}")
            else:
                await conn.execute(
                    """
                    INSERT INTO jurisdictions (id, city, state, county, country_code, display_name, level, authority_type)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'geographic')
                    """,
                    jurisdiction_id, city, state, county, country, display_name, level,
                )

                # Auto-link to national parent for non-US jurisdictions
                if country != "US":
                    national_parent = await conn.fetchrow(
                        "SELECT id FROM jurisdictions WHERE country_code = $1 AND level = 'national' LIMIT 1",
                        country,
                    )
                    if national_parent:
                        await conn.execute(
                            "UPDATE jurisdictions SET parent_id = $1 WHERE id = $2",
                            national_parent["id"], jurisdiction_id,
                        )

                print(f"CREATED:{jurisdiction_id}:{city}:{state or ''}:{county or ''}:{country}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
