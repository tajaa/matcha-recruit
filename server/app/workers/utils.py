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
