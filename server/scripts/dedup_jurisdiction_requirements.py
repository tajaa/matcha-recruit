"""
One-time dedup of jurisdiction_requirements rows that map to the same canonical key.

Usage:
    python -m server.scripts.dedup_jurisdiction_requirements --dry-run
    python -m server.scripts.dedup_jurisdiction_requirements --apply
"""

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_connection, init_pool, close_pool
from app.config import load_settings
from app.core.services.compliance_service import (
    _compute_requirement_key,
)


def _score_row(row) -> tuple:
    """Score a row for quality — higher is better. Returns tuple for sorting."""
    val_len = len(row["current_value"] or "")
    has_citation = 1 if row.get("statute_citation") else 0
    has_source = 1 if row.get("source_url") else 0
    has_numeric = 1 if row.get("numeric_value") is not None else 0
    return (has_citation, has_source, has_numeric, val_len)


async def run(dry_run: bool):
    settings = load_settings()
    await init_pool(settings.database_url)
    try:
        await _run(dry_run)
    finally:
        await close_pool()


async def _run(dry_run: bool):
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT id, jurisdiction_id, category, title, current_value,
                   jurisdiction_level, jurisdiction_name, rate_type,
                   statute_citation, source_url, numeric_value,
                   regulation_key, requirement_key,
                   applicable_entity_types
            FROM jurisdiction_requirements
            WHERE superseded_by_id IS NULL
            ORDER BY jurisdiction_id, category, title
        """)

        print(f"Total active rows: {len(rows)}")

        # Group by (jurisdiction_id, category) then compute new keys
        by_jid_cat: dict[tuple, list] = defaultdict(list)
        for r in rows:
            by_jid_cat[(r["jurisdiction_id"], r["category"])].append(dict(r))

        total_dupes = 0
        total_groups = 0
        actions: list[tuple[str, str]] = []  # (superseded_id, winner_id)

        for (jid, cat), group in sorted(by_jid_cat.items()):
            # Compute new keys for each row
            by_new_key: dict[str, list] = defaultdict(list)
            for row in group:
                new_key = _compute_requirement_key(row)
                by_new_key[new_key].append(row)

            for new_key, dupes in by_new_key.items():
                if len(dupes) <= 1:
                    continue

                total_groups += 1
                # Pick the best row
                dupes.sort(key=_score_row, reverse=True)
                winner = dupes[0]
                losers = dupes[1:]
                total_dupes += len(losers)

                jname = winner.get("jurisdiction_name", "?")
                print(f"\n{'[DRY RUN] ' if dry_run else ''}Duplicate group: {jname} / {cat} / key={new_key}")
                print(f"  KEEP: {winner['title']!r} (id={winner['id']})")
                for loser in losers:
                    print(f"  DROP: {loser['title']!r} (id={loser['id']})")
                    actions.append((str(loser["id"]), str(winner["id"])))

        print(f"\n{'=' * 60}")
        print(f"Duplicate groups: {total_groups}")
        print(f"Rows to supersede: {total_dupes}")

        if dry_run or not actions:
            if not actions:
                print("No duplicates found.")
            else:
                print("Run with --apply to execute.")
            return

        # Apply: set superseded_by_id and update requirement_key on winners
        async with conn.transaction():
            for loser_id, winner_id in actions:
                await conn.execute(
                    "UPDATE jurisdiction_requirements SET superseded_by_id = $1 WHERE id = $2",
                    winner_id, loser_id,
                )

            # Also update requirement_key on all active rows to use new canonical keys
            active = await conn.fetch("""
                SELECT id, category, title, jurisdiction_name, rate_type,
                       regulation_key, requirement_key, applicable_entity_types
                FROM jurisdiction_requirements
                WHERE superseded_by_id IS NULL
            """)
            updated_keys = 0
            for row in active:
                new_key = _compute_requirement_key(dict(row))
                if new_key != row["requirement_key"]:
                    await conn.execute(
                        "UPDATE jurisdiction_requirements SET requirement_key = $1 WHERE id = $2",
                        new_key, row["id"],
                    )
                    updated_keys += 1

            print(f"Superseded {len(actions)} rows")
            print(f"Updated {updated_keys} requirement_keys to canonical form")


def main():
    parser = argparse.ArgumentParser(description="Deduplicate jurisdiction requirements")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show what would be deduplicated")
    group.add_argument("--apply", action="store_true", help="Apply deduplication")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
