#!/usr/bin/env python3
"""
Bootstrap a new jurisdiction: create the DB row and research all compliance categories.

Usage:
    python scripts/bootstrap_jurisdiction.py "Indianapolis" "IN"
    python scripts/bootstrap_jurisdiction.py "Indianapolis" "IN" --county "Marion"
    python scripts/bootstrap_jurisdiction.py "Indianapolis" "IN" --categories healthcare
    python scripts/bootstrap_jurisdiction.py "Indianapolis" "IN" --dry-run
    python scripts/bootstrap_jurisdiction.py "Indianapolis" "IN" --output /tmp/custom.md

Creates the jurisdiction in the database, then researches compliance requirements
via Gemini and writes results to a Markdown file.

Use --dry-run to skip the DB insert and only produce the Markdown output.
"""

import argparse
import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

# Add server root to path so we can import app modules
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
    parser = argparse.ArgumentParser(
        description="Bootstrap a new jurisdiction and research its compliance requirements"
    )
    parser.add_argument("city", help="City name (e.g. 'Indianapolis')")
    parser.add_argument("state", help="Two-letter state code (e.g. 'IN')")
    parser.add_argument("--county", help="County name (e.g. 'Marion')")
    parser.add_argument(
        "--categories",
        action="append",
        default=[],
        help="Category groups: general, healthcare, oncology, medical_compliance, all (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Research and write Markdown only — do NOT create the jurisdiction in the DB",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: scripts/<city>_<state>_compliance.md)",
    )
    args = parser.parse_args()

    city = args.city.strip().title()
    state = args.state.strip().upper()
    county = args.county.strip().title() if args.county else None
    groups = [g.lower() for g in args.categories] if args.categories else ["all"]

    # Validate state code
    if state not in US_STATE_CODES:
        print(f"ERROR: '{state}' is not a valid US state code.")
        print("Use a two-letter code like CA, NY, IN, TX, etc.")
        return

    from app.core.compliance_registry import (
        LABOR_CATEGORIES,
        HEALTHCARE_CATEGORIES,
        ONCOLOGY_CATEGORIES,
        MEDICAL_COMPLIANCE_CATEGORIES,
        CATEGORY_LABELS,
    )

    # Resolve target category keys
    target_keys: Set[str] = set()
    for g in groups:
        if g == "all":
            target_keys |= LABOR_CATEGORIES | HEALTHCARE_CATEGORIES | ONCOLOGY_CATEGORIES
        elif g == "general":
            target_keys |= LABOR_CATEGORIES
        elif g == "healthcare":
            target_keys |= HEALTHCARE_CATEGORIES
        elif g == "oncology":
            target_keys |= ONCOLOGY_CATEGORIES
        elif g == "medical_compliance":
            target_keys |= MEDICAL_COMPLIANCE_CATEGORIES
        else:
            target_keys.add(g)

    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            # ── Step 1: Check if jurisdiction already exists ──
            existing = await conn.fetchrow(
                "SELECT id, city, state, county FROM jurisdictions "
                "WHERE LOWER(city) = LOWER($1) AND state = $2",
                city, state,
            )

            if existing:
                print(f"Jurisdiction already exists: {existing['city']}, {existing['state']}")
                print(f"  ID: {existing['id']}")
                print(f"  County: {existing['county'] or 'N/A'}")
                print("\nUse /fill-gaps to research missing categories for existing jurisdictions.")
                return

            # ── Step 2: Create jurisdiction ──
            jurisdiction_id = uuid.uuid4()
            display_name = f"{city}, {state}"

            if args.dry_run:
                print(f"[DRY RUN] Would create jurisdiction: {display_name}")
                print(f"  ID: {jurisdiction_id}")
                print(f"  County: {county or 'N/A'}")
            else:
                await conn.execute(
                    """
                    INSERT INTO jurisdictions (id, city, state, county, display_name, level, authority_type)
                    VALUES ($1, $2, $3, $4, $5, 'city', 'geographic')
                    """,
                    jurisdiction_id, city, state, county, display_name,
                )
                print(f"Created jurisdiction: {display_name}")
                print(f"  ID: {jurisdiction_id}")
                print(f"  County: {county or 'N/A'}")

            # ── Step 3: Research compliance categories ──
            categories_to_research = sorted(target_keys)
            print(f"\nResearching {len(categories_to_research)} categories via Gemini...\n")

            from app.core.services.gemini_compliance import get_gemini_compliance_service
            from app.core.services.jurisdiction_context import (
                get_global_authority_sources,
            )
            from app.core.services.compliance_service import (
                _lookup_has_local_ordinance,
            )

            service = get_gemini_compliance_service()
            has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)

            # Build source context — no known sources for a new jurisdiction,
            # but add global authority sources for healthcare/oncology
            source_context = ""
            healthcare_cats = [c for c in categories_to_research if c in HEALTHCARE_CATEGORIES]
            oncology_cats = [c for c in categories_to_research if c in ONCOLOGY_CATEGORIES]
            medical_cats = [c for c in categories_to_research if c in MEDICAL_COMPLIANCE_CATEGORIES]
            if healthcare_cats:
                source_context += get_global_authority_sources(healthcare_cats)
            if oncology_cats:
                source_context += get_global_authority_sources(oncology_cats)
            if medical_cats:
                source_context += get_global_authority_sources(medical_cats)

            # No corrections for a brand-new jurisdiction
            corrections_context = ""

            # Fetch state preemption rules
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

            for idx, category in enumerate(categories_to_research, start=1):
                label = CATEGORY_LABELS.get(category, category)
                print(f"  [{idx}/{len(categories_to_research)}] {category} ({label})...", end=" ", flush=True)
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

            # ── Step 4: Write Markdown ──
            total_reqs = sum(len(v) for v in all_results.values())
            group_label = "/".join(groups)
            output_path = args.output or str(
                Path(__file__).parent / f"{city.lower().replace(' ', '_')}_{state.lower()}_compliance.md"
            )

            lines: List[str] = []
            lines.append(f"# {city}, {state} — Compliance Requirements\n")
            if not args.dry_run:
                lines.append(f"**Jurisdiction ID**: `{jurisdiction_id}`")
            else:
                lines.append(f"**Mode**: DRY RUN (jurisdiction not created in DB)")
            lines.append(f"**Researched**: {date.today().isoformat()}")
            lines.append(f"**County**: {county or 'N/A'}")
            lines.append(f"**Groups**: {group_label}")
            lines.append(f"**Categories researched**: {len(categories_to_research)}")
            lines.append(f"**Total requirements found**: {total_reqs}")
            if failed:
                lines.append(f"**Failed categories**: {', '.join(failed)}")
            lines.append("")
            lines.append("---\n")

            cat_num = 0
            for category in categories_to_research:
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
                    if req.get("applicable_industries"):
                        industries = req["applicable_industries"]
                        if isinstance(industries, list):
                            lines.append(f"- **Applicable Industries**: {', '.join(industries)}")
                        else:
                            lines.append(f"- **Applicable Industries**: {industries}")
                    if req.get("applicable_entity_types"):
                        lines.append(f"- **Applicable Entity Types**: {', '.join(req['applicable_entity_types'])}")
                    lines.append("")

            md_content = "\n".join(lines)

            with open(output_path, "w") as f:
                f.write(md_content)

            print(f"\n{'='*60}")
            if args.dry_run:
                print(f"[DRY RUN] Jurisdiction NOT created in DB")
            else:
                print(f"Jurisdiction created: {display_name} ({jurisdiction_id})")
            print(f"Written to: {output_path}")
            print(f"Total: {total_reqs} requirements across {len(categories_to_research)} categories")
            if failed:
                print(f"Failed: {', '.join(failed)}")
            print(f"{'='*60}")

    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
