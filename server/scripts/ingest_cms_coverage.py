#!/usr/bin/env python3
"""
Ingest Medicare coverage data from the CMS Coverage API.

Bulk-imports NCDs, LCDs, and their associated billing articles with
CPT/ICD code mappings into payer_medical_policies.

Usage:
    cd server
    python scripts/ingest_cms_coverage.py
    python scripts/ingest_cms_coverage.py --ncds-only
    python scripts/ingest_cms_coverage.py --lcds-only --state CA
    python scripts/ingest_cms_coverage.py --dry-run
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SKIP_REDIS", "1")


async def main():
    parser = argparse.ArgumentParser(description="Ingest CMS Medicare coverage data")
    parser.add_argument("--ncds-only", action="store_true", help="Only ingest NCDs")
    parser.add_argument("--lcds-only", action="store_true", help="Only ingest LCDs")
    parser.add_argument("--state", type=str, help="Filter LCDs by state (e.g., CA)")
    parser.add_argument("--embed", action="store_true", help="Also embed policies after ingestion")
    parser.add_argument("--dry-run", action="store_true", help="Count available documents without ingesting")
    args = parser.parse_args()

    from app.config import load_settings
    from app.database import init_pool, get_pool, get_connection
    from app.core.services.cms_coverage_api import CMSCoverageAPI

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()
    api = CMSCoverageAPI()

    print("Accepting CMS license agreement...")
    token = await api.get_license_token()
    print(f"Token obtained: {token[:8]}...")

    if args.dry_run:
        ncds = await api.list_ncds()
        print(f"NCDs available: {len(ncds)}")
        lcds = await api.list_lcds(state=args.state)
        print(f"LCDs available: {len(lcds)}")
        await pool.close()
        return

    async with get_connection() as conn:
        all_changes = []

        if not args.lcds_only:
            print("\n=== Ingesting NCDs ===")
            ncd_summary = await api.ingest_all_ncds(conn)
            all_changes.extend(ncd_summary.get("changes", []))

        if not args.ncds_only:
            print(f"\n=== Ingesting LCDs{' (state: ' + args.state + ')' if args.state else ''} ===")
            lcd_summary = await api.ingest_all_lcds(conn, state=args.state)
            all_changes.extend(lcd_summary.get("changes", []))

        if all_changes:
            print(f"\n=== {len(all_changes)} CHANGES DETECTED ===")
            for ch in all_changes:
                print(f"  {ch['policy_number']}: {ch['policy_title']} — changed: {', '.join(ch['fields_changed'])}")

        if args.embed:
            print("\n=== Embedding policies ===")
            from app.core.services.payer_policy_embedding_pipeline import embed_policies
            embed_count = await embed_policies(conn, payer_name="Medicare")
            print(f"Policies embedded: {embed_count}")

        # Final count
        row_count = await conn.fetchval("SELECT COUNT(*) FROM payer_medical_policies")
        embed_count_db = await conn.fetchval("SELECT COUNT(*) FROM payer_policy_embeddings")
        print(f"\nDatabase totals: {row_count} policies, {embed_count_db} embeddings")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
