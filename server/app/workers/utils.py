"""Shared utilities for Celery worker tasks."""

import asyncio
import json
import logging
import os
import ssl as _ssl
from typing import Any, Awaitable, TypeVar

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


logger = logging.getLogger(__name__)
_T = TypeVar("_T")


async def _with_chat_fanout(coro: Awaitable[_T]) -> _T:
    from app.core.services import redis_cache

    opened = False
    if redis_cache.get_redis_cache() is None:
        try:
            await redis_cache.init_redis_cache(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            opened = True
        except Exception:
            logger.warning("worker Redis client failed to open; chat posts will wait for a reload", exc_info=True)
    try:
        return await coro
    finally:
        if opened:
            await redis_cache.close_redis_cache()


def run_with_chat_fanout(coro: Awaitable[_T]) -> _T:
    """`asyncio.run` for a task that posts to chat or sockets.

    The socket fanout (`channels_ws.manager`) publishes on the shared Redis
    client, which only the API opens, in its lifespan. Without one a worker's
    chat message is saved but reaches open chats only on their next reload.
    The client can't be opened once per worker process: each task runs its own
    `asyncio.run` loop and an asyncio Redis client is bound to the loop it
    first connects on (the same reason workers have no DB pool). So the task
    entry opens it on the task's own loop, and closes it after. Opening is
    lazy (no connection until the first publish), so a task that posts
    nothing costs nothing."""
    return asyncio.run(_with_chat_fanout(coro))


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
