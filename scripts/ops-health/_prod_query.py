"""Read-only production queries run inside the active backend container.

The wrapper supplies this file on stdin via ``docker exec`` so GitHub Actions
never needs production database credentials.  Keep the queries narrow and
structured: their JSON is copied into GitHub workflow artifacts and issues.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import asyncpg


async def _domains(conn: asyncpg.Connection) -> dict:
    rows = await conn.fetch(
        """
        SELECT domain
        FROM cappe_domains
        WHERE status = 'active'
        ORDER BY domain
        """
    )
    return {"domains": [row["domain"] for row in rows]}


async def _errors(conn: asyncpg.Connection) -> dict:
    rows = await conn.fetch(
        """
        SELECT id::text, fingerprint, kind, level, exception_type, message,
               traceback, source, request_method, request_path, request_status,
               occurrences, first_seen, last_seen, resolved_at
        FROM server_error_reports
        WHERE level IN ('ERROR', 'CRITICAL')
          AND last_seen > NOW() - INTERVAL '2 hours'
        ORDER BY last_seen DESC
        """
    )
    return {
        "errors": [
            {
                "id": row["id"],
                "fingerprint": row["fingerprint"],
                "kind": row["kind"],
                "level": row["level"],
                "exception_type": row["exception_type"],
                "message": row["message"],
                "traceback": row["traceback"],
                "source": row["source"],
                "request_method": row["request_method"],
                "request_path": row["request_path"],
                "request_status": row["request_status"],
                "occurrences": row["occurrences"],
                "first_seen": row["first_seen"].isoformat(),
                "last_seen": row["last_seen"].isoformat(),
                "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
            }
            for row in rows
        ]
    }


async def main() -> None:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode not in {"domains", "errors"}:
        raise SystemExit("usage: _prod_query.py domains|errors")

    conn = await asyncpg.connect(
        os.environ["DATABASE_URL"],
        server_settings={"default_transaction_read_only": "on"},
    )
    try:
        await conn.execute("SET statement_timeout = '15s'")
        result = await (_domains(conn) if mode == "domains" else _errors(conn))
    finally:
        await conn.close()
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    asyncio.run(main())
