"""Seed CA WC class codes (description + advisory pure premium rate) into
wc_class_codes from ca_wc_class_codes_2026.csv.

Idempotent upsert on (state, class_code). Run against dev, or use the admin
"import class codes" endpoint in prod (same CSV columns). Reads DATABASE_URL
from server/.env unless DATABASE_URL is already set; pass --url to override.

    cd server && ./venv/bin/python scripts/wc_data/seed_ca_wc_class_codes.py
"""

import asyncio
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "ca_wc_class_codes_2026.csv")
SOURCE = "WCIRB 9/1/2026 advisory pure premium"


def _db_url() -> str:
    for a in sys.argv[1:]:
        if a.startswith("--url="):
            return a.split("=", 1)[1]
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env = os.path.join(HERE, "..", "..", ".env")
    if os.path.exists(env):
        m = re.search(r"^DATABASE_URL=(.*)$", open(env).read(), re.M)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit("set DATABASE_URL or pass --url=postgresql://…")


async def main() -> None:
    import asyncpg

    url = _db_url()
    rows = list(csv.DictReader(open(CSV_PATH)))
    conn = await asyncpg.connect(url)
    try:
        n = 0
        for r in rows:
            rate = float(r["base_rate"]) if r.get("base_rate") else None
            await conn.execute(
                """
                INSERT INTO wc_class_codes (state, class_code, description, base_rate, source)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT ON CONSTRAINT uq_wc_class_code DO UPDATE SET
                    description = EXCLUDED.description, base_rate = EXCLUDED.base_rate, source = EXCLUDED.source
                """,
                (r.get("state") or "CA").strip().upper()[:2], r["class_code"].strip(),
                r["description"][:255], rate, SOURCE,
            )
            n += 1
        total = await conn.fetchval("SELECT count(*) FROM wc_class_codes WHERE state = 'CA'")
        print(f"upserted {n} rows · CA class codes now: {total}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
