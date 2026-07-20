"""Shared utilities for Celery worker tasks."""

import json
import os
import ssl as _ssl
from typing import Any

import asyncpg
from dotenv import load_dotenv

load_dotenv()


def _make_ssl_context(mode: str):
    """Build an SSL context for asyncpg based on the requested mode."""
    if mode == "disable":
        return None
    if mode == "require":
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        return ctx
    if mode == "verify-full":
        return _ssl.create_default_context()
    return None


async def get_db_connection() -> asyncpg.Connection:
    """Create a database connection for the worker."""
    database_url = os.getenv("DATABASE_URL", "").strip().strip('"')
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable not set")
    ssl_ctx = _make_ssl_context(os.getenv("DATABASE_SSL", "disable"))
    return await asyncpg.connect(database_url, ssl=ssl_ctx)


def parse_jsonb(value: Any) -> Any:
    """Parse JSONB value from database."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


async def scheduler_settings_row(conn, task_key: str):
    """The `scheduler_settings` row for a task, or None.

    Guards against the table not existing yet (deploy ordering) — the reason
    every caller wrapped this fetch in its own try/except.

    Most scheduled tasks need `max_per_cycle` alongside `enabled`, so this
    returns the row and lets the caller read what it needs; `scheduler_enabled`
    is the convenience wrapper for the two tasks that only gate.
    """
    try:
        return await conn.fetchrow(
            "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key = $1",
            task_key,
        )
    except Exception:
        return None


async def scheduler_enabled(conn, task_key: str, *, default: bool = True) -> bool:
    """Is the `scheduler_settings` row for this task enabled?

    Returns only a bool rather than owning the early return: each task answers a
    disabled scheduler with its OWN result payload (`{"checked": 0}`,
    `{"threads": 0, "projects": 0, "skipped": True}`, `{"status": "disabled"}`,
    …), and flattening those would change what every caller reports.

    `default` is what a MISSING row (or a failed query) means, and it is explicit
    because the tasks genuinely disagree — this is not a detail to standardise:

      * fail OPEN (`default=True`) — auto_archive, coi_expiry, discipline_expiry,
        newsletter_scheduler. Idempotent bookkeeping; a transient DB hiccup
        silently disabling them is worse than one extra run.
      * fail CLOSED (`default=False`) — cappe_domain_renewals (buys domain
        renewals) and vertical_coverage_sweep (makes live Gemini calls and is
        seeded disabled on purpose). For these, "we could not read the setting"
        must not mean "go ahead and spend money".
    """
    row = await scheduler_settings_row(conn, task_key)
    if row is None:
        return default
    return bool(row["enabled"])
