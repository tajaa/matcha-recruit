#!/usr/bin/env python3
"""
Output jurisdiction research context — same data the Gemini compliance scripts use.

Usage:
    python scripts/jurisdiction_context.py "Sacramento" "CA"
    python scripts/jurisdiction_context.py "Singapore" --country SG
    python scripts/jurisdiction_context.py "Mexico City" "CDMX" --country MX

Outputs JSON with:
  - has_local_ordinance: whether city has local employment ordinances (US only)
  - preemption_rules: {category: allows_local_override} from state_preemption_rules (US only)
  - expected_keys: {category: [regulation_keys]} from compliance_registry
  - category_labels: {category_key: "Human Label"}
  - groups: {group_name: [category_keys]}
  - country_code: ISO 3166-1 alpha-2
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SKIP_REDIS", "1")


async def main():
    parser = argparse.ArgumentParser(description="Get jurisdiction research context")
    parser.add_argument("city", help="City name")
    parser.add_argument("state", nargs="?", default=None, help="State/province code (optional for city-states)")
    parser.add_argument("--country", default="US", help="ISO 3166-1 alpha-2 country code (default: US)")
    args = parser.parse_args()

    city = args.city.strip().title()
    state = args.state.strip().upper() if args.state else None
    country = args.country.strip().upper()

    from app.core.compliance_registry import (
        LABOR_CATEGORIES,
        HEALTHCARE_CATEGORIES,
        ONCOLOGY_CATEGORIES,
        CATEGORY_LABELS,
        EXPECTED_REGULATION_KEYS,
    )
    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    has_local = False
    preemption = {}
    intl_key_rows = []

    try:
        async with pool.acquire() as conn:
            if country == "US" and state:
                # US-specific: check local ordinance and preemption rules
                from app.core.services.compliance_service import _lookup_has_local_ordinance
                has_local = await _lookup_has_local_ordinance(conn, city, state)

                try:
                    rows = await conn.fetch(
                        "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                        state,
                    )
                    preemption = {r["category"]: r["allows_local_override"] for r in rows}
                except Exception:
                    preemption = {}
            else:
                # International: query regulation_key_definitions filtered by applicable_countries
                intl_key_rows = await conn.fetch("""
                    SELECT category_slug, key FROM regulation_key_definitions
                    WHERE (applicable_countries IS NULL OR $1 = ANY(applicable_countries))
                    ORDER BY category_slug, key
                """, country)
    finally:
        await close_pool()

    # Build expected keys (only for the 25 categories we research)
    target_cats = sorted(LABOR_CATEGORIES | HEALTHCARE_CATEGORIES | ONCOLOGY_CATEGORIES)
    expected = {}

    if country != "US":
        from app.core.compliance_registry import _key_applies_to_country
        for r in intl_key_rows:
            if r["category_slug"] in target_cats:
                # Double-filter: DB query handles applicable_countries column,
                # Python filter handles keys not yet tagged in DB (legacy US keys
                # with applicable_countries=NULL that shouldn't appear for intl)
                if _key_applies_to_country(r["key"], r["category_slug"], country):
                    expected.setdefault(r["category_slug"], []).append(r["key"])
    else:
        # US: use Python registry (all keys apply)
        for cat in target_cats:
            keys = EXPECTED_REGULATION_KEYS.get(cat, frozenset())
            if keys:
                expected[cat] = sorted(keys)

    output = {
        "city": city,
        "state": state,
        "country_code": country,
        "has_local_ordinance": has_local,
        "preemption_rules": preemption,
        "groups": {
            "labor": sorted(LABOR_CATEGORIES),
            "healthcare": sorted(HEALTHCARE_CATEGORIES),
            "oncology": sorted(ONCOLOGY_CATEGORIES),
        },
        "category_labels": {k: CATEGORY_LABELS[k] for k in target_cats},
        "expected_regulation_keys": expected,
    }

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
