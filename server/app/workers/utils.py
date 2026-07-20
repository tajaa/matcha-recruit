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


async def scheduler_enabled(conn, task_key: str) -> bool:
    """Is the `scheduler_settings` row for this task enabled?

    Every scheduled task inlines this same fetch + swallow-and-default. The
    helper deliberately returns only a bool rather than owning the early return:
    each task answers a disabled scheduler with its OWN result payload
    (`{"checked": 0}`, `{"threads": 0, "projects": 0, "skipped": True}`,
    `{"status": "disabled"}`, …), and flattening those would change what every
    caller reports.

    Fails OPEN, matching the behaviour it replaces: a missing row (task never
    configured) or a failed query means enabled. The tasks are idempotent and a
    transient DB hiccup silently disabling the scheduler would be far worse than
    one extra run. Takes an open connection — workers are pool-free.
    """
    try:
        row = await conn.fetchrow(
            "SELECT enabled FROM scheduler_settings WHERE task_key = $1", task_key
        )
    except Exception:
        return True
    if row is None:
        return True
    return bool(row["enabled"])
