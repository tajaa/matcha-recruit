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
    _normalize_title_key,
)


def _same_obligation(a, b) -> bool:
    """Are these two rows the SAME obligation (a true duplicate), or two DIFFERENT
    obligations that merely collided on one key?

    Sharing a regulation_key is NOT sufficient. Dev holds real collisions —
    'Federal COBRA' vs 'Cal-COBRA' (both cobra_continuation), 'Statutory Sick Leave'
    vs 'Maternity Leave' (both statutory_sick_leave), 'MIPS' vs 'Adverse Event
    Reporting' (both mips_qpp). Superseding one of those DELETES a live obligation.

    So we only merge on a positive identity signal — the same normalized title.
    Everything else is a KEY COLLISION: reported, never dropped; the remedy is
    re-keying the mis-keyed row, which a human/curation pass must decide.
    """
    return _normalize_title_key(a.get("title") or "") == _normalize_title_key(b.get("title") or "")


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
        total_collisions = 0
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
                # Pick the best row as the reference
                dupes.sort(key=_score_row, reverse=True)
                winner = dupes[0]
                jname = winner.get("jurisdiction_name", "?")

                # Split the rest: true duplicates (same obligation) get merged;
                # different obligations sharing one key are COLLISIONS — the
                # polymorphy failure mode — and must be re-keyed, never dropped.
                losers = [d for d in dupes[1:] if _same_obligation(winner, d)]
                colliders = [d for d in dupes[1:] if not _same_obligation(winner, d)]
                total_dupes += len(losers)

                print(f"\n{'[DRY RUN] ' if dry_run else ''}Group: {jname} / {cat} / key={new_key}")
                print(f"  KEEP: {winner['title']!r} (id={winner['id']})")
                for loser in losers:
                    print(f"  MERGE (same obligation): {loser['title']!r} (id={loser['id']})")
                    actions.append((str(loser["id"]), str(winner["id"])))
                for c in colliders:
                    total_collisions += 1
                    print(f"  ⚠ KEY COLLISION (different obligation, NOT dropped): "
                          f"{c['title']!r} (id={c['id']}) — needs re-key")

        print(f"\n{'=' * 60}")
        print(f"Groups examined: {total_groups}")
        print(f"True duplicates to supersede: {total_dupes}")
        print(f"Key collisions needing re-key (untouched): {total_collisions}")

        if dry_run or not actions:
            if not actions:
                print("No duplicates found.")
            else:
                print("Run with --apply to execute.")
            return

        # Apply: retire losers and re-key survivors to the canonical composite.
        async with conn.transaction():
            for loser_id, winner_id in actions:
                # status='superseded' matters: every catalog reader filters
                # `WHERE status='active'`, NOT `superseded_by_id IS NULL`, so
                # setting only the pointer would leave the loser visible.
                await conn.execute(
                    "UPDATE jurisdiction_requirements "
                    "SET superseded_by_id = $1, status = 'superseded' WHERE id = $2",
                    winner_id, loser_id,
                )

            # Re-key all surviving rows to the canonical composite so a future
            # upsert hits ON CONFLICT (UPDATE) instead of minting a twin.
            # jurisdiction_level is load-bearing — normalize_key uses it to pick
            # state_/local_/national_minimum_wage; omitting it mis-keys the row.
            active = await conn.fetch("""
                SELECT jr.id, jr.jurisdiction_id, jr.category, jr.title,
                       jr.jurisdiction_name, jr.rate_type,
                       jr.jurisdiction_level, COALESCE(j.country_code, 'US') AS country_code,
                       jr.regulation_key, jr.requirement_key, jr.applicable_entity_types
                FROM jurisdiction_requirements jr
                JOIN jurisdictions j ON j.id = jr.jurisdiction_id
                WHERE jr.superseded_by_id IS NULL
            """)
            taken = {(r["jurisdiction_id"], r["requirement_key"]) for r in active}
            updated_keys = 0
            skipped_taken = 0
            for row in active:
                new_key = _compute_requirement_key(dict(row))
                if new_key == row["requirement_key"]:
                    continue
                # A collider recomputes to a key another active row already holds
                # (that IS the collision). Re-keying it would violate the unique
                # index — leave it on its old key until curation re-keys it.
                if (row["jurisdiction_id"], new_key) in taken:
                    skipped_taken += 1
                    continue
                await conn.execute(
                    "UPDATE jurisdiction_requirements SET requirement_key = $1 WHERE id = $2",
                    new_key, row["id"],
                )
                taken.discard((row["jurisdiction_id"], row["requirement_key"]))
                taken.add((row["jurisdiction_id"], new_key))
                updated_keys += 1

            print(f"Superseded {len(actions)} rows")
            print(f"Updated {updated_keys} requirement_keys to canonical form")
            print(f"Skipped {skipped_taken} re-keys (canonical key already taken — collision, needs curation)")


def main():
    parser = argparse.ArgumentParser(description="Deduplicate jurisdiction requirements")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show what would be deduplicated")
    group.add_argument("--apply", action="store_true", help="Apply deduplication")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
