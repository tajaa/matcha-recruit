"""
One-time backfill for the admin_updates table (migration adminupd01) — the
changelog shown at /admin/updates, previously a static frontend TS file
(client/src/data/adminUpdates.ts). Reads scripts/data/admin_updates_seed.json
(a straight dump of the old ADMIN_UPDATES array) and upserts every row.

Idempotent: safe to re-run — existing ids are updated in place, position is
re-derived from the JSON file's array order every run.

Run with: python scripts/seed_admin_updates.py
"""
import asyncio
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.database import init_pool, close_pool, get_connection

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "admin_updates_seed.json")


async def seed_admin_updates():
    settings = load_settings()
    await init_pool(settings.database_url)

    with open(DATA_PATH) as f:
        updates = json.load(f)

    async with get_connection() as conn:
        for position, u in enumerate(updates):
            await conn.execute(
                """
                INSERT INTO admin_updates
                    (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (id) DO UPDATE SET
                    position = EXCLUDED.position,
                    date = EXCLUDED.date,
                    category = EXCLUDED.category,
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    whats_new = EXCLUDED.whats_new,
                    how_to_use = EXCLUDED.how_to_use,
                    setup = EXCLUDED.setup,
                    notes = EXCLUDED.notes,
                    tag = EXCLUDED.tag
                """,
                u["id"],
                position,
                date.fromisoformat(u["date"]),
                u["category"],
                u["title"],
                u["summary"],
                json.dumps(u["whatsNew"]),
                json.dumps(u["howToUse"]),
                json.dumps(u["setup"]) if u.get("setup") is not None else None,
                json.dumps(u["notes"]) if u.get("notes") is not None else None,
                u.get("tag"),
            )
        count = await conn.fetchval("SELECT count(*) FROM admin_updates")
        print(f"admin_updates: {count} rows")

    await close_pool()


if __name__ == "__main__":
    asyncio.run(seed_admin_updates())
