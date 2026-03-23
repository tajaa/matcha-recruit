#!/usr/bin/env python3
"""
Output jurisdiction research context — same data the Gemini compliance scripts use.

Usage:
    python scripts/jurisdiction_context.py "Sacramento" "CA"

Outputs JSON with:
  - has_local_ordinance: whether city has local employment ordinances
  - preemption_rules: {category: allows_local_override} from state_preemption_rules
  - expected_keys: {category: [regulation_keys]} from compliance_registry
  - category_labels: {category_key: "Human Label"}
  - groups: {group_name: [category_keys]}
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
    parser.add_argument("state", help="Two-letter state code")
    args = parser.parse_args()

    city = args.city.strip().title()
    state = args.state.strip().upper()

    from app.core.compliance_registry import (
        LABOR_CATEGORIES,
        HEALTHCARE_CATEGORIES,
        ONCOLOGY_CATEGORIES,
        CATEGORY_LABELS,
        EXPECTED_REGULATION_KEYS,
    )
    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool
    from app.core.services.compliance_service import _lookup_has_local_ordinance

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            has_local = await _lookup_has_local_ordinance(conn, city, state)

            try:
                rows = await conn.fetch(
                    "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                    state,
                )
                preemption = {r["category"]: r["allows_local_override"] for r in rows}
            except Exception:
                preemption = {}

    finally:
        await close_pool()

    # Build expected keys (only for the 25 categories we research)
    target_cats = sorted(LABOR_CATEGORIES | HEALTHCARE_CATEGORIES | ONCOLOGY_CATEGORIES)
    expected = {}
    for cat in target_cats:
        keys = EXPECTED_REGULATION_KEYS.get(cat, frozenset())
        if keys:
            expected[cat] = sorted(keys)

    output = {
        "city": city,
        "state": state,
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
