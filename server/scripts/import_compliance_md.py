#!/usr/bin/env python3
"""
Import compliance requirements from Markdown files into jurisdiction_requirements.

Parses MD files produced by fill_jurisdiction_gaps.py (or manually written) and
inserts requirements using the same _upsert_requirements_additive() function
the UI buttons use.

Usage:
    # Dry run — parse and show what would be inserted:
    python scripts/import_compliance_md.py --dry-run scripts/los_angeles_ca_compliance.md

    # Actually import:
    python scripts/import_compliance_md.py scripts/los_angeles_ca_compliance.md

    # Import multiple files:
    python scripts/import_compliance_md.py scripts/san_diego_ca_compliance.md scripts/austin_tx_compliance.md
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SKIP_REDIS", "1")


# ── Field name mapping ──────────────────────────────────────────────
FIELD_MAP = {
    "Title": "title",
    "Regulation Key": "regulation_key",
    "Description": "description",
    "Current Value": "current_value",
    "Rate Type": "rate_type",
    "Numeric Value": "numeric_value",
    "Jurisdiction Level": "jurisdiction_level",
    "Jurisdiction Name": "jurisdiction_name",
    "Requires Written Policy": "requires_written_policy",
    "Effective Date": "effective_date",
    "Source URL": "source_url",
    "Source Name": "source_name",
    "Applicable Industries": "applicable_industries",
    "Applicable Entity Types": "applicable_entity_types",
    "Paid": "paid",
    "Max Weeks": "max_weeks",
    "Wage Replacement %": "wage_replacement_pct",
    "Job Protection": "job_protection",
    "Employer Size Threshold": "employer_size_threshold",
}

# Fields to skip (informational only, not part of upsert)
SKIP_FIELDS = {"Citation", "Category"}


def _strip_backticks(s: str) -> str:
    """Remove surrounding backticks from a string."""
    return s.strip("`")


def _parse_bool(val: str) -> Optional[bool]:
    """Parse a boolean string, returning None for null/None."""
    lower = val.strip().lower()
    if lower in ("true", "yes"):
        return True
    if lower in ("false", "no"):
        return False
    if lower in ("null", "none", ""):
        return None
    return None


def _parse_float(val: str) -> Optional[float]:
    """Parse a float string, returning None for null/None."""
    val = val.strip()
    if val.lower() in ("null", "none", "n/a", ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _parse_int(val: str) -> Optional[int]:
    """Parse an int string, returning None for null/None."""
    val = val.strip()
    if val.lower() in ("null", "none", "n/a", ""):
        return None
    try:
        return int(float(val))
    except ValueError:
        return None


def _parse_string_or_none(val: str) -> Optional[str]:
    """Return string value, or None if null/None/N/A."""
    val = val.strip()
    if val.lower() in ("null", "none"):
        return None
    return val if val else None


def _parse_list(val: str) -> Optional[list]:
    """Parse a list value — handles JSON arrays or comma-separated strings."""
    val = val.strip()
    if val.lower() in ("null", "none", "n/a", ""):
        return None

    # Try JSON array first: ["a", "b"]
    if val.startswith("["):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    # Fallback: comma-separated
    items = [item.strip().strip('"').strip("'") for item in val.split(",")]
    return [item for item in items if item]


def _convert_field(field_key: str, raw_value: str):
    """Convert a raw string value to the appropriate Python type for the given field."""
    if field_key == "regulation_key":
        return _strip_backticks(raw_value)
    if field_key in ("requires_written_policy", "paid", "job_protection"):
        return _parse_bool(raw_value)
    if field_key == "numeric_value":
        return _parse_float(raw_value)
    if field_key == "wage_replacement_pct":
        return _parse_float(raw_value)
    if field_key in ("max_weeks", "employer_size_threshold"):
        return _parse_int(raw_value)
    if field_key in ("applicable_industries", "applicable_entity_types"):
        return _parse_list(raw_value)
    if field_key == "effective_date":
        return _parse_string_or_none(raw_value)
    # Default: string (with null handling)
    return _parse_string_or_none(raw_value)


# ── Regex patterns ──────────────────────────────────────────────────
RE_JURISDICTION_ID = re.compile(r"\*\*Jurisdiction ID\*\*:\s*`([0-9a-f-]{36})`")
RE_CATEGORY_HEADING = re.compile(r"^##\s+\d+\.\s+`([^`]+)`")
RE_REQUIREMENT_HEADING = re.compile(r"^###\s+(.+)")
RE_FIELD_LINE = re.compile(r"^-\s+\*\*([^*]+)\*\*:\s*(.+)$")

# Headings that signal the end of parseable requirement data
STOP_HEADINGS = {"SQL Insert Notes", "Sources", "Notes"}


def parse_md_file(filepath: str) -> tuple[Optional[UUID], List[Dict]]:
    """
    Parse a compliance MD file and return (jurisdiction_id, list_of_requirement_dicts).

    Each requirement dict has all the fields needed for _upsert_requirements_additive(),
    including 'category' set from the ## heading section.
    """
    with open(filepath, "r") as f:
        lines = f.readlines()

    jurisdiction_id: Optional[UUID] = None
    current_category: Optional[str] = None
    current_req: Optional[Dict] = None
    requirements: List[Dict] = []

    for line in lines:
        line = line.rstrip("\n")

        # Extract jurisdiction ID from header
        if jurisdiction_id is None:
            m = RE_JURISDICTION_ID.search(line)
            if m:
                jurisdiction_id = UUID(m.group(1))
                continue

        # Stop at non-data sections (Sources, SQL Insert Notes, etc.)
        if line.startswith("## ") and not RE_CATEGORY_HEADING.match(line):
            heading_text = line.lstrip("# ").strip()
            if heading_text in STOP_HEADINGS:
                if current_req:
                    requirements.append(current_req)
                    current_req = None
                break

        # Category heading: ## N. `category_key`
        m = RE_CATEGORY_HEADING.match(line)
        if m:
            # Save any in-progress requirement
            if current_req:
                requirements.append(current_req)
                current_req = None
            current_category = m.group(1)
            continue

        # Requirement heading: ### Title
        m = RE_REQUIREMENT_HEADING.match(line)
        if m:
            # Save any in-progress requirement
            if current_req:
                requirements.append(current_req)
            current_req = {"category": current_category, "title": m.group(1).strip()}
            continue

        # Field line: - **Field**: value
        m = RE_FIELD_LINE.match(line)
        if m and current_req is not None:
            field_name = m.group(1).strip()
            raw_value = m.group(2).strip()

            if field_name in SKIP_FIELDS:
                continue

            dict_key = FIELD_MAP.get(field_name)
            if dict_key is None:
                # Unknown field — skip silently
                continue

            # Don't overwrite category from bullet — it comes from the ## heading
            if dict_key == "category":
                continue

            current_req[dict_key] = _convert_field(dict_key, raw_value)

    # Don't forget the last requirement
    if current_req:
        requirements.append(current_req)

    return jurisdiction_id, requirements


def print_dry_run(filepath: str, jurisdiction_id: Optional[UUID], requirements: List[Dict]):
    """Print a dry-run summary showing parsed requirements and their computed keys."""
    from app.core.services.compliance_service import _compute_requirement_key

    print(f"\nParsed: {len(requirements)} requirements from {filepath}")
    if jurisdiction_id:
        print(f"Jurisdiction: {jurisdiction_id}")
    else:
        print("WARNING: No Jurisdiction ID found in file!")

    if not requirements:
        print("  (no requirements parsed)\n")
        return

    # Group by category
    by_category: Dict[str, List[Dict]] = {}
    for req in requirements:
        cat = req.get("category", "unknown")
        by_category.setdefault(cat, []).append(req)

    print()
    for category in sorted(by_category.keys()):
        reqs = by_category[category]
        print(f"  {category} ({len(reqs)} requirements):")
        for req in reqs:
            key = _compute_requirement_key(req)
            title = req.get("title", "Untitled")
            print(f'    -> {key}  "{title}"')
        print()


async def import_file(filepath: str, dry_run: bool = False):
    """Parse and optionally import a single MD file."""
    jurisdiction_id, requirements = parse_md_file(filepath)

    if not jurisdiction_id:
        print(f"ERROR: No Jurisdiction ID found in {filepath}")
        return False

    if not requirements:
        print(f"WARNING: No requirements parsed from {filepath}")
        return False

    if dry_run:
        print_dry_run(filepath, jurisdiction_id, requirements)
        return True

    # Actual import
    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool
    from app.core.services.compliance_service import _upsert_requirements_additive

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            # Verify jurisdiction exists
            row = await conn.fetchrow(
                "SELECT city, state FROM jurisdictions WHERE id = $1",
                jurisdiction_id,
            )
            if not row:
                print(f"ERROR: Jurisdiction {jurisdiction_id} not found in database!")
                return False

            city = row["city"]
            state = row["state"]
            print(f"\nImporting {len(requirements)} requirements into jurisdiction {jurisdiction_id} ({city}, {state})")

            # Group by category and upsert
            by_category: Dict[str, List[Dict]] = {}
            for req in requirements:
                cat = req.get("category", "unknown")
                by_category.setdefault(cat, []).append(req)

            total = 0
            for category in sorted(by_category.keys()):
                reqs = by_category[category]
                print(f"  {category}: {len(reqs)} upserted")
                await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="claude_skill")
                total += len(reqs)

            print(f"\nDone: {total} requirements upserted across {len(by_category)} categories.")

    finally:
        await close_pool()

    return True


async def main():
    parser = argparse.ArgumentParser(
        description="Import compliance requirements from Markdown into jurisdiction_requirements"
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="One or more Markdown files to import",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only — print what would be inserted, no DB writes",
    )
    args = parser.parse_args()

    # Validate all files exist before starting
    for filepath in args.files:
        if not Path(filepath).exists():
            print(f"ERROR: File not found: {filepath}")
            sys.exit(1)

    success_count = 0
    for filepath in args.files:
        ok = await import_file(filepath, dry_run=args.dry_run)
        if ok:
            success_count += 1

    if len(args.files) > 1:
        print(f"\n{'='*60}")
        print(f"Processed {success_count}/{len(args.files)} files successfully.")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
