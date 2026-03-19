"""One-time backfill: tag existing federal-source requirements with research_source metadata.

Usage:
    cd server && python -m scripts.backfill_research_source

Or from repo root:
    python scripts/backfill_research_source.py
"""

import asyncio
import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

import asyncpg


async def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        # Try loading from .env
        env_path = os.path.join(os.path.dirname(__file__), "..", "server", ".env")
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not database_url:
        print("ERROR: DATABASE_URL not set and not found in server/.env")
        sys.exit(1)

    conn = await asyncpg.connect(database_url)
    try:
        result = await conn.execute("""
            UPDATE jurisdiction_requirements
            SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"research_source": "official_api"}'::jsonb
            WHERE (source_name LIKE 'Federal Register%'
               OR source_name = 'CMS Provider Data'
               OR source_name = 'Congress.gov')
              AND (metadata IS NULL OR metadata->>'research_source' IS NULL)
        """)
        count = int(result.split()[-1]) if result else 0
        print(f"Backfilled {count} rows with research_source = 'official_api'")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
