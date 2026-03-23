#!/usr/bin/env python3
"""
Ingest a compliance research markdown file into jurisdiction_requirements.

Usage:
    python scripts/ingest_research_md.py scripts/london_gb_research.md --jurisdiction-id <UUID>
    python scripts/ingest_research_md.py scripts/charlotte_nc_research.md --city Charlotte --state NC
    python scripts/ingest_research_md.py scripts/london_gb_research.md --city London --state ENG --country GB
    python scripts/ingest_research_md.py scripts/london_gb_research.md --city London --country GB --dry-run

Parses the structured markdown format (regulation_key, jurisdiction_level, etc.)
and upserts into jurisdiction_requirements.
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SKIP_REDIS", "1")


def parse_research_md(filepath: str) -> List[Dict]:
    """Parse a research markdown file into requirement dicts."""
    with open(filepath) as f:
        content = f.read()

    requirements = []
    current_category = None
    current_req: Optional[Dict] = None

    for line in content.split("\n"):
        line = line.rstrip()

        # Category header: ### minimum_wage or ## minimum_wage
        cat_match = re.match(r'^#{2,3}\s+(\w+)\s*$', line)
        if cat_match:
            candidate = cat_match.group(1)
            # Only treat as category if it looks like a slug (lowercase, underscores)
            if candidate == candidate.lower() and '_' in candidate:
                current_category = candidate
                continue

        # Requirement header: #### Title
        req_match = re.match(r'^#{4}\s+(.+)$', line)
        if req_match and current_category:
            if current_req and current_req.get("regulation_key"):
                requirements.append(current_req)
            current_req = {
                "category": current_category,
                "title": req_match.group(1).strip(),
            }
            continue

        # Field: - **field_name**: value
        field_match = re.match(r'^-\s+\*\*(\w[\w\s]*)\*\*:\s*(.+)$', line)
        if field_match and current_req is not None:
            field = field_match.group(1).strip().lower().replace(" ", "_")
            value = field_match.group(2).strip()

            # Strip backticks from values
            value = value.strip('`')

            if field == "regulation_key":
                current_req["regulation_key"] = value
            elif field == "jurisdiction_level":
                current_req["jurisdiction_level"] = value
            elif field == "jurisdiction_name":
                current_req["jurisdiction_name"] = value
            elif field == "description":
                current_req["description"] = value
            elif field == "current_value":
                current_req["current_value"] = value
            elif field == "numeric_value":
                try:
                    current_req["numeric_value"] = float(value)
                except (ValueError, TypeError):
                    pass
            elif field == "effective_date":
                current_req["effective_date"] = value if value != "N/A" else None
            elif field == "source_url":
                current_req["source_url"] = value
            elif field == "source_name":
                current_req["source_name"] = value
            elif field == "requires_written_policy":
                current_req["requires_written_policy"] = value.lower() == "true"
            elif field == "rate_type":
                current_req["rate_type"] = value
            elif field == "paid":
                current_req["paid"] = value.lower() == "true"
            elif field == "max_weeks":
                try:
                    current_req["max_weeks"] = value
                except (ValueError, TypeError):
                    pass
            elif field == "wage_replacement_pct" or field == "wage_replacement_%":
                current_req["wage_replacement_pct"] = value
            elif field == "job_protection":
                current_req["job_protection"] = value.lower() == "true"
            elif field == "employer_size_threshold":
                current_req["employer_size_threshold"] = value

    # Don't forget the last requirement
    if current_req and current_req.get("regulation_key"):
        requirements.append(current_req)

    return requirements


async def main():
    parser = argparse.ArgumentParser(description="Ingest research markdown into jurisdiction_requirements")
    parser.add_argument("file", help="Path to the research markdown file")
    parser.add_argument("--jurisdiction-id", help="Jurisdiction UUID (if known)")
    parser.add_argument("--city", help="City name")
    parser.add_argument("--state", help="State/province code")
    parser.add_argument("--country", default="US", help="Country code (default: US)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print, don't insert")
    args = parser.parse_args()

    reqs = parse_research_md(args.file)
    print(f"Parsed {len(reqs)} requirements from {args.file}")

    if not reqs:
        print("No requirements found. Check the markdown format.")
        return

    # Show summary by category
    cats: Dict[str, int] = {}
    for r in reqs:
        cats[r.get("category", "unknown")] = cats.get(r.get("category", "unknown"), 0) + 1
    for cat, count in sorted(cats.items()):
        print(f"  {cat}: {count}")

    if args.dry_run:
        print("\n[DRY RUN] Would insert these requirements:")
        for r in reqs:
            print(f"  {r.get('category')}:{r.get('regulation_key')} — {r.get('title')}")
        return

    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool
    from app.core.services.compliance_service import _compute_requirement_key

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            # Resolve jurisdiction
            if args.jurisdiction_id:
                from uuid import UUID
                jurisdiction_id = UUID(args.jurisdiction_id)
            elif args.city:
                city = args.city.strip().title()
                state = args.state.strip().upper() if args.state else None
                country = args.country.strip().upper()
                row = await conn.fetchrow(
                    "SELECT id FROM jurisdictions WHERE LOWER(city) = LOWER($1) AND COALESCE(state, '') = COALESCE($2, '') AND country_code = $3",
                    city, state or '', country,
                )
                if not row:
                    print(f"ERROR: Jurisdiction not found: {city}, {state or ''}, {country}")
                    return
                jurisdiction_id = row["id"]
            else:
                print("ERROR: Provide --jurisdiction-id or --city (+ --state/--country)")
                return

            print(f"\nInserting into jurisdiction {jurisdiction_id}...")

            # Pre-fetch category_id map
            cat_rows = await conn.fetch("SELECT id, slug FROM compliance_categories")
            cat_id_map = {r["slug"]: r["id"] for r in cat_rows}

            inserted = 0
            skipped = 0
            for r in reqs:
                req_key = _compute_requirement_key(r)
                category = r.get("category", "")
                category_id = cat_id_map.get(category)
                if not category_id:
                    print(f"  SKIP {category}:{r.get('regulation_key')}: unknown category '{category}'")
                    skipped += 1
                    continue

                try:
                    effective_date = None
                    if r.get("effective_date"):
                        from datetime import date as dt_date
                        try:
                            effective_date = dt_date.fromisoformat(r["effective_date"])
                        except (ValueError, TypeError):
                            pass

                    result = await conn.execute("""
                        INSERT INTO jurisdiction_requirements
                            (jurisdiction_id, requirement_key, category, category_id, jurisdiction_level,
                             jurisdiction_name, title, description, current_value,
                             numeric_value, source_url, source_name, effective_date,
                             rate_type, requires_written_policy, regulation_key)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                        ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                            title = EXCLUDED.title,
                            description = EXCLUDED.description,
                            current_value = EXCLUDED.current_value,
                            numeric_value = EXCLUDED.numeric_value,
                            source_url = EXCLUDED.source_url,
                            source_name = EXCLUDED.source_name,
                            effective_date = EXCLUDED.effective_date,
                            last_verified_at = NOW(),
                            updated_at = NOW()
                    """,
                        jurisdiction_id,
                        req_key,
                        category,
                        category_id,
                        r.get("jurisdiction_level", "state"),
                        r.get("jurisdiction_name", ""),
                        r.get("title", "Untitled"),
                        r.get("description"),
                        r.get("current_value"),
                        r.get("numeric_value"),
                        r.get("source_url"),
                        r.get("source_name"),
                        effective_date,
                        r.get("rate_type"),
                        r.get("requires_written_policy", False),
                        r.get("regulation_key"),
                    )
                    inserted += 1
                except Exception as e:
                    print(f"  SKIP {r.get('category')}:{r.get('regulation_key')}: {e}")
                    skipped += 1

            # Update requirement_count
            count = await conn.fetchval(
                "SELECT count(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                jurisdiction_id,
            )
            await conn.execute(
                "UPDATE jurisdictions SET requirement_count = $1, last_verified_at = NOW(), updated_at = NOW() WHERE id = $2",
                count, jurisdiction_id,
            )

            # Link to key_definition_id where possible
            await conn.execute("""
                UPDATE jurisdiction_requirements jr
                SET key_definition_id = rkd.id
                FROM regulation_key_definitions rkd
                WHERE jr.jurisdiction_id = $1
                  AND jr.category = rkd.category_slug
                  AND jr.regulation_key = rkd.key
                  AND jr.key_definition_id IS NULL
            """, jurisdiction_id)

            linked = await conn.fetchval(
                "SELECT count(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1 AND key_definition_id IS NOT NULL",
                jurisdiction_id,
            )

            print(f"\nDone: {inserted} inserted/updated, {skipped} skipped")
            print(f"Total requirements: {count}")
            print(f"Linked to key definitions: {linked}")

    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
