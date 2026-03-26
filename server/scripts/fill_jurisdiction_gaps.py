#!/usr/bin/env python3
"""
Fill missing compliance categories for a jurisdiction and write results to Markdown.

Usage:
    python scripts/fill_jurisdiction_gaps.py "San Diego" "CA"
    python scripts/fill_jurisdiction_gaps.py "San Diego" "CA" --list-gaps
    python scripts/fill_jurisdiction_gaps.py "San Diego" "CA" --categories healthcare
    python scripts/fill_jurisdiction_gaps.py "San Diego" "CA" --categories oncology --categories general
    python scripts/fill_jurisdiction_gaps.py "San Diego" "CA" --output /tmp/custom_output.md

Writes a Markdown file to server/scripts/<city>_<state>_compliance.md by default.
Does NOT write to the database.
"""

import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

# Add server root to path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SKIP_REDIS", "1")


async def main():
    parser = argparse.ArgumentParser(description="Research compliance gaps → Markdown")
    parser.add_argument("city", help="City name (e.g. 'San Diego')")
    parser.add_argument("state", help="State code (e.g. 'CA')")
    parser.add_argument(
        "--categories",
        action="append",
        default=[],
        help="Category groups to research: general, healthcare, oncology, life_sciences, manufacturing, all (default: all)",
    )
    parser.add_argument("--list-gaps", action="store_true", help="Just list what's missing, don't research")
    parser.add_argument("--output", "-o", help="Output file path (default: scripts/<city>_<state>_compliance.md)")
    args = parser.parse_args()

    city = args.city.strip()
    state = args.state.strip().upper()
    groups = [g.lower() for g in args.categories] if args.categories else ["all"]

    from app.core.compliance_registry import (
        CATEGORIES,
        LABOR_CATEGORIES,
        HEALTHCARE_CATEGORIES,
        ONCOLOGY_CATEGORIES,
        LIFE_SCIENCES_CATEGORIES,
        MANUFACTURING_CATEGORIES,
        CATEGORY_LABELS,
    )

    # Resolve which category keys to target
    target_keys: Set[str] = set()
    for g in groups:
        if g == "all":
            target_keys |= LABOR_CATEGORIES | HEALTHCARE_CATEGORIES | ONCOLOGY_CATEGORIES | LIFE_SCIENCES_CATEGORIES | MANUFACTURING_CATEGORIES
        elif g == "general":
            target_keys |= LABOR_CATEGORIES
        elif g == "healthcare":
            target_keys |= HEALTHCARE_CATEGORIES
        elif g == "oncology":
            target_keys |= ONCOLOGY_CATEGORIES
        elif g == "life_sciences":
            target_keys |= LIFE_SCIENCES_CATEGORIES
        elif g == "manufacturing":
            target_keys |= MANUFACTURING_CATEGORIES
        else:
            # Treat as a literal category key
            target_keys.add(g)

    # Connect to DB to find the jurisdiction and check existing coverage
    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            if city == "" or city.lower() == "none":
                # State-level jurisdiction (city is NULL)
                row = await conn.fetchrow(
                    "SELECT id, city, state, county FROM jurisdictions WHERE city IS NULL AND state = $1",
                    state,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT id, city, state, county FROM jurisdictions WHERE LOWER(city) = LOWER($1) AND state = $2",
                    city, state,
                )
            if not row:
                print(f"Jurisdiction not found: {city}, {state}")
                print("Searching for close matches...")
                close = await conn.fetch(
                    "SELECT city, state FROM jurisdictions WHERE state = $1 AND city ILIKE $2 LIMIT 10",
                    state, f"%{city}%",
                )
                if close:
                    for r in close:
                        print(f"  - {r['city']}, {r['state']}")
                return

            jurisdiction_id = row["id"]
            county = row["county"]
            location_name = f"{city}, {state}" if city else f"{state} (state)"

            # Check what already exists in jurisdiction_requirements
            existing_rows = await conn.fetch(
                "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                jurisdiction_id,
            )
            existing_cats = {r["category"] for r in existing_rows}

            # Determine what's missing
            missing = sorted(cat for cat in target_keys if cat not in existing_cats)
            present = sorted(cat for cat in target_keys if cat in existing_cats)

            print(f"\n{'='*60}")
            print(f"Jurisdiction: {location_name} (county: {county or 'N/A'})")
            print(f"ID: {jurisdiction_id}")
            print(f"Target categories: {len(target_keys)}")
            print(f"Already present: {len(present)}")
            print(f"Missing: {len(missing)}")
            print(f"{'='*60}\n")

            if present:
                print("Present:")
                for cat in present:
                    label = CATEGORY_LABELS.get(cat, cat)
                    print(f"  ✓ {cat} ({label})")

            if missing:
                print("\nMissing:")
                for cat in missing:
                    label = CATEGORY_LABELS.get(cat, cat)
                    print(f"  ✗ {cat} ({label})")
            else:
                print("\nNo gaps — all target categories are present.")

            if args.list_gaps or not missing:
                return

            # Research missing categories via Gemini
            print(f"\nResearching {len(missing)} categories via Gemini...\n")

            from app.core.services.gemini_compliance import get_gemini_compliance_service
            from app.core.services.jurisdiction_context import (
                get_known_sources,
                build_context_prompt,
                get_global_authority_sources,
            )
            from app.core.services.compliance_service import (
                _lookup_has_local_ordinance,
                get_recent_corrections,
                format_corrections_for_prompt,
            )

            service = get_gemini_compliance_service()
            has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
            known_sources = await get_known_sources(conn, jurisdiction_id)
            source_context = build_context_prompt(known_sources)

            # Add global authority sources for healthcare/oncology
            healthcare_missing = [c for c in missing if c in HEALTHCARE_CATEGORIES]
            oncology_missing = [c for c in missing if c in ONCOLOGY_CATEGORIES]
            if healthcare_missing:
                source_context += get_global_authority_sources(healthcare_missing)
            if oncology_missing:
                source_context += get_global_authority_sources(oncology_missing)

            corrections = await get_recent_corrections(jurisdiction_id)
            corrections_context = format_corrections_for_prompt(corrections)

            try:
                preemption_rows = await conn.fetch(
                    "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                    state,
                )
                preemption_rules = {r["category"]: r["allows_local_override"] for r in preemption_rows}
            except Exception:
                preemption_rules = {}

            # Research each category
            all_results: Dict[str, List[Dict]] = {}
            failed: List[str] = []

            for idx, category in enumerate(missing, start=1):
                label = CATEGORY_LABELS.get(category, category)
                print(f"  [{idx}/{len(missing)}] {category} ({label})...", end=" ", flush=True)
                try:
                    reqs = await service.research_location_compliance(
                        city=city,
                        state=state,
                        county=county,
                        categories=[category],
                        source_context=source_context,
                        corrections_context=corrections_context,
                        preemption_rules=preemption_rules,
                        has_local_ordinance=has_local_ordinance,
                    )
                    reqs = reqs or []
                    all_results[category] = reqs
                    print(f"{len(reqs)} requirements")
                except Exception as e:
                    failed.append(category)
                    all_results[category] = []
                    print(f"FAILED ({e})")

            # Write markdown
            total_reqs = sum(len(v) for v in all_results.values())
            group_label = "/".join(groups)
            output_path = args.output or str(
                Path(__file__).parent / f"{city.lower().replace(' ', '_')}_{state.lower()}_compliance.md"
            )

            lines: List[str] = []
            lines.append(f"# {city}, {state} — Compliance Requirements\n")
            lines.append(f"**Jurisdiction ID**: `{jurisdiction_id}`")
            lines.append(f"**Researched**: {date.today().isoformat()}")
            lines.append(f"**Groups**: {group_label}")
            lines.append(f"**Categories researched**: {len(missing)}")
            lines.append(f"**Total requirements found**: {total_reqs}")
            if failed:
                lines.append(f"**Failed categories**: {', '.join(failed)}")
            lines.append("")
            lines.append("---\n")

            cat_num = 0
            for category in missing:
                reqs = all_results.get(category, [])
                cat_num += 1
                label = CATEGORY_LABELS.get(category, category)
                lines.append(f"## {cat_num}. `{category}` — {label}\n")

                if not reqs:
                    status = "FAILED" if category in failed else "No requirements found"
                    lines.append(f"*{status}*\n")
                    continue

                for req in reqs:
                    title = req.get("title", "Untitled")
                    lines.append(f"### {title}\n")
                    lines.append(f"- **Category**: {req.get('category', category)}")
                    if req.get("regulation_key"):
                        lines.append(f"- **Regulation Key**: `{req['regulation_key']}`")
                    if req.get("rate_type"):
                        lines.append(f"- **Rate Type**: {req['rate_type']}")
                    lines.append(f"- **Description**: {req.get('description', 'N/A')}")
                    lines.append(f"- **Current Value**: {req.get('current_value', 'N/A')}")
                    if req.get("numeric_value") is not None:
                        lines.append(f"- **Numeric Value**: {req['numeric_value']}")
                    lines.append(f"- **Jurisdiction Level**: {req.get('jurisdiction_level', 'N/A')}")
                    lines.append(f"- **Jurisdiction Name**: {req.get('jurisdiction_name', 'N/A')}")
                    lines.append(f"- **Requires Written Policy**: {req.get('requires_written_policy', False)}")
                    if req.get("effective_date"):
                        lines.append(f"- **Effective Date**: {req['effective_date']}")
                    if req.get("source_url"):
                        lines.append(f"- **Source URL**: {req['source_url']}")
                    if req.get("source_name"):
                        lines.append(f"- **Source Name**: {req['source_name']}")
                    # Leave-specific fields
                    if req.get("paid") is not None:
                        lines.append(f"- **Paid**: {req['paid']}")
                    if req.get("max_weeks") is not None:
                        lines.append(f"- **Max Weeks**: {req['max_weeks']}")
                    if req.get("wage_replacement_pct") is not None:
                        lines.append(f"- **Wage Replacement %**: {req['wage_replacement_pct']}")
                    if req.get("job_protection") is not None:
                        lines.append(f"- **Job Protection**: {req['job_protection']}")
                    if req.get("employer_size_threshold") is not None:
                        lines.append(f"- **Employer Size Threshold**: {req['employer_size_threshold']}")
                    # Industry tags
                    if req.get("applicable_industries"):
                        industries = req["applicable_industries"]
                        if isinstance(industries, list):
                            lines.append(f"- **Applicable Industries**: {', '.join(industries)}")
                        else:
                            lines.append(f"- **Applicable Industries**: {industries}")
                    # Trigger info
                    if req.get("applicable_entity_types"):
                        lines.append(f"- **Applicable Entity Types**: {', '.join(req['applicable_entity_types'])}")
                    lines.append("")

            md_content = "\n".join(lines)

            with open(output_path, "w") as f:
                f.write(md_content)

            print(f"\n{'='*60}")
            print(f"Written to: {output_path}")
            print(f"Total: {total_reqs} requirements across {len(missing)} categories")
            if failed:
                print(f"Failed: {', '.join(failed)}")
            print(f"{'='*60}")

    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
