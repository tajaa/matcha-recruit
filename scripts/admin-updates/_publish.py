"""Trusted, fixed-shape production publisher executed inside the backend."""

import asyncio
import base64
import json
import os
from datetime import date

from app.database import connection_or_direct


TABLES = {"matcha": "admin_updates", "tellus": "tellus_admin_updates"}


async def main() -> None:
    payload = json.loads(base64.b64decode(os.environ["ADMIN_UPDATES_PAYLOAD_B64"]))
    entries = payload["entries"]
    target = int(payload["processedThroughPr"])
    inserted = {"matcha": 0, "tellus": 0}

    async with connection_or_direct(force_direct=True) as conn:
        async with conn.transaction():
            for index, entry in enumerate(entries):
                product = entry["product"]
                table = TABLES[product]
                result = await conn.execute(
                    f"""
                    INSERT INTO {table}
                        (id, position, date, category, title, summary,
                         whats_new, how_to_use, setup, notes, tag)
                    VALUES ($1, $2, $3::date, $4, $5, $6, $7::jsonb,
                            $8::jsonb, NULL, $9::jsonb, $10)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    entry["id"],
                    -100000 + index,
                    date.fromisoformat(entry["date"]),
                    entry["category"],
                    entry["title"],
                    entry["summary"],
                    json.dumps(entry["whatsNew"]),
                    json.dumps(entry["howToUse"]),
                    json.dumps(entry["notes"]) if entry["notes"] is not None else None,
                    entry["tag"],
                )
                if result == "INSERT 0 1":
                    inserted[product] += 1

            for table in TABLES.values():
                await conn.execute(f"""
                    WITH ordered AS (
                        SELECT id,
                               row_number() OVER (
                                   ORDER BY date DESC, position ASC, created_at ASC, id ASC
                               ) - 1 AS position
                        FROM {table}
                    )
                    UPDATE {table} target
                    SET position = ordered.position
                    FROM ordered
                    WHERE target.id = ordered.id
                      AND target.position IS DISTINCT FROM ordered.position
                """)

            await conn.execute(
                """
                INSERT INTO changelog_autogen_state (id, last_pr_number, updated_at)
                VALUES (1, $1, now())
                ON CONFLICT (id) DO UPDATE
                SET last_pr_number = GREATEST(
                        changelog_autogen_state.last_pr_number,
                        EXCLUDED.last_pr_number
                    ),
                    updated_at = now()
                """,
                target,
            )
            current = await conn.fetchval(
                "SELECT last_pr_number FROM changelog_autogen_state WHERE id = 1"
            )

    print(json.dumps({
        "schema_version": 1,
        "processed_through_pr": current,
        "inserted": inserted,
        "submitted_entries": len(entries),
    }))


if __name__ == "__main__":
    asyncio.run(main())
