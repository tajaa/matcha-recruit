"""app.database.pool — asyncpg pool lifecycle + tenant/user/admin contextvars.

Verbatim split of app/database.py lines 1-200 (one rewritten import: line 140
`from .config import get_settings` -> `from app.config import get_settings`,
since this module is now one package level deeper).
"""
import contextvars
import json
import ssl as _ssl
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None

# ── Request-scoped tenant context (set by auth dependencies) ──────────
_tenant_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "tenant_id", default=""
)
_user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_id", default=""
)
_is_admin_var: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "is_admin", default=False
)


def set_tenant_id(value: str) -> None:
    _tenant_id_var.set(value)


def get_tenant_id() -> str:
    return _tenant_id_var.get()


def set_user_id(value: str) -> None:
    _user_id_var.set(value)


def get_user_id() -> str:
    return _user_id_var.get()


def set_is_admin(value: bool) -> None:
    _is_admin_var.set(value)


def get_is_admin() -> bool:
    return _is_admin_var.get()


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


async def init_pool(database_url: str, *, ssl_mode: str = "disable"):
    """Initialize the connection pool."""
    global _pool
    if _pool is None:
        ssl_ctx = _make_ssl_context(ssl_mode)
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            max_inactive_connection_lifetime=60,
            command_timeout=30,
            ssl=ssl_ctx,
        )
    return _pool


async def get_pool() -> asyncpg.Pool:
    """Get the existing connection pool."""
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool first.")
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def has_pool() -> bool:
    """Is the app connection pool initialized in this process?

    False inside Celery workers, which are pool-free BY DESIGN (see the NOTE in
    workers/celery_app.py: each task runs its own asyncio.run() loop, and an
    asyncpg pool bound to a different loop cannot be reused).
    """
    return _pool is not None


@asynccontextmanager
async def connection_or_direct(*, force_direct: bool = False):
    """A connection that works in BOTH the API and a Celery worker.

    For code on the SHARED service path that cannot know which world it is running
    in. The Gemini rate limiter is the load-bearing case: every AI call in the
    codebase passes through it, and it hard-required the pool — so **no Celery task
    could ever call Gemini**. It failed at `check_limit`, before the API call, and
    surfaced only as a research pass that mysteriously produced nothing.

    Pooled connection when a pool exists; otherwise a raw one, opened and closed
    per use inside the caller's own loop.

    `force_direct` skips the pool even when one exists. Needed by callers running
    on a DIFFERENT event loop than the one the pool was created on — an asyncpg
    pool's connections are bound to their creating loop, and using one from a
    foreign loop raises "got Future attached to a different loop". The live case
    is a blocking SDK call inside `asyncio.to_thread` that then spins up its own
    `asyncio.run()` to record telemetry (see `ai_usage._record`).

    Prefer plain `get_connection()` on request paths, and pass an explicit `conn`
    down worker paths. This is for the narrow middle: shared code with no caller
    context.
    """
    if _pool is not None and not force_direct:
        async with get_connection() as conn:
            yield conn
        return

    # Env first, settings second: a Celery worker may not have called
    # load_settings() (get_settings() raises when it hasn't), but DATABASE_URL is
    # always in its environment — it is how workers/utils.get_db_connection works.
    import os

    database_url = os.getenv("DATABASE_URL", "").strip().strip('"')
    ssl_mode = os.getenv("DATABASE_SSL", "disable")
    if not database_url:
        from app.config import get_settings

        settings = get_settings()
        database_url = settings.database_url
        ssl_mode = getattr(settings, "database_ssl", "disable") or "disable"

    conn = await asyncpg.connect(database_url, ssl=_make_ssl_context(ssl_mode))
    try:
        yield conn
    finally:
        await conn.close()


@asynccontextmanager
async def get_connection(tenant_id: str | None = None):
    """Get a database connection from the pool.

    Args:
        tenant_id: Optional company/org UUID string. When provided, sets
            ``app.current_tenant_id`` for the duration of the connection so
            that PostgreSQL row-level security policies can filter rows
            automatically.  The setting is session-level (connection-scoped)
            and is reset when the connection returns to the pool.
    """
    pool = await get_pool()
    effective_tenant = tenant_id or _tenant_id_var.get() or None
    effective_user = _user_id_var.get() or None
    is_admin = _is_admin_var.get()

    async with pool.acquire() as conn:
        if effective_tenant:
            await conn.execute(
                "SELECT set_config('app.current_tenant_id', $1, false)",
                str(effective_tenant),
            )
        if effective_user:
            await conn.execute(
                "SELECT set_config('app.current_user_id', $1, false)",
                str(effective_user),
            )
        if is_admin:
            await conn.execute(
                "SELECT set_config('app.is_admin', 'true', false)"
            )
        try:
            yield conn
        finally:
            if effective_tenant:
                await conn.execute(
                    "SELECT set_config('app.current_tenant_id', '', false)"
                )
            if effective_user:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', '', false)"
                )
            if is_admin:
                await conn.execute(
                    "SELECT set_config('app.is_admin', '', false)"
                )


