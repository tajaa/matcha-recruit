"""Shared utilities for Celery worker tasks."""

import json
import os
from typing import Any

import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def get_db_connection() -> asyncpg.Connection:
    """Create a database connection for the worker."""
    database_url = os.getenv("DATABASE_URL", "")
    return await asyncpg.connect(database_url)


def parse_jsonb(value: Any) -> Any:
    """Parse JSONB value from database."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value
