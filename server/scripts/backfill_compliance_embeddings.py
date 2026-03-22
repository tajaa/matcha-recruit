#!/usr/bin/env python3
"""
Backfill compliance embeddings for all existing jurisdiction_requirements.

One-time script to vectorize all requirements for regulatory Q&A RAG search.

Usage:
    cd server
    python scripts/backfill_compliance_embeddings.py
    python scripts/backfill_compliance_embeddings.py --jurisdiction-id <uuid>
    python scripts/backfill_compliance_embeddings.py --dry-run
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

# Add server root to path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SKIP_REDIS", "1")


async def main():
    parser = argparse.ArgumentParser(description="Backfill compliance embeddings")
    parser.add_argument("--jurisdiction-id", type=str, help="Only embed this jurisdiction")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for embedding API calls")
    parser.add_argument("--dry-run", action="store_true", help="Count requirements without embedding")
    args = parser.parse_args()

    from app.config import load_settings
    from app.database import init_pool, get_pool, get_connection
    from app.core.services.compliance_embedding_pipeline import embed_requirements

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    async with get_connection() as conn:
        # Count requirements
        jid = UUID(args.jurisdiction_id) if args.jurisdiction_id else None
        where = "WHERE jurisdiction_id = $1" if jid else ""
        params = [jid] if jid else []
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM jurisdiction_requirements {where}", *params
        )
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM compliance_embeddings"
        )
        print(f"Jurisdiction requirements: {total}")
        print(f"Existing embeddings: {existing}")
        print(f"To embed: {total - existing} (new) + {existing} (update)")

        if args.dry_run:
            print("Dry run — exiting.")
            return

        print(f"\nStarting backfill with batch_size={args.batch_size}...")
        count = await embed_requirements(
            conn, jurisdiction_id=jid, batch_size=args.batch_size,
        )
        print(f"\nDone. Embedded {count} requirements.")

        final_count = await conn.fetchval(
            "SELECT COUNT(*) FROM compliance_embeddings"
        )
        print(f"Total embeddings in table: {final_count}")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
