"""Read only the production changelog ids and automation watermark."""

import asyncio
import json

from app.database import connection_or_direct


async def main() -> None:
    async with connection_or_direct(force_direct=True) as conn:
        async with conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            state = await conn.fetchrow(
                "SELECT last_pr_number, updated_at FROM changelog_autogen_state WHERE id = 1"
            )
            matcha_ids = await conn.fetch("SELECT id FROM admin_updates ORDER BY id")
            tellus_ids = await conn.fetch("SELECT id FROM tellus_admin_updates ORDER BY id")

    print(json.dumps({
        "schema_version": 1,
        "last_pr_number": state["last_pr_number"] if state else None,
        "updated_at": state["updated_at"].isoformat() if state and state["updated_at"] else None,
        "existing": {
            "matcha": [row["id"] for row in matcha_ids],
            "tellus": [row["id"] for row in tellus_ids],
        },
    }))


if __name__ == "__main__":
    asyncio.run(main())
