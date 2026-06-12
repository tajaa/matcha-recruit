"""Shared helpers for the Cappe routers."""
import json
import re
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, status

# asyncpg returns JSONB columns as text (no global codec is registered), so
# every JSONB read goes through _loads and every write through json.dumps.

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, hyphenate, strip. Falls back to 'site' when empty."""
    s = _SLUG_RE.sub("-", (text or "").strip().lower()).strip("-")
    return s[:140] or "site"


async def unique_slug(conn, base: str, table: str, column: str = "slug") -> str:
    """Return `base`, or `base-2`, `base-3`, … until it's free in table.column.

    Table/column are caller-controlled literals (never user input), so the
    f-string is safe; the value is always parameterized.
    """
    candidate = base
    n = 1
    while True:
        exists = await conn.fetchval(
            f"SELECT 1 FROM {table} WHERE {column} = $1", candidate
        )
        if not exists:
            return candidate
        n += 1
        candidate = f"{base}-{n}"


def loads(value: Any) -> dict:
    """Normalize a JSONB read (str | dict | None) into a dict."""
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


async def get_owned_site(conn, site_id: UUID, account_id: UUID):
    """Fetch a site row, 404ing if it doesn't exist or isn't this account's.

    Same id is returned for missing-vs-forbidden so we never leak which site
    ids exist across accounts.
    """
    row = await conn.fetchrow(
        "SELECT * FROM cappe_sites WHERE id = $1 AND account_id = $2",
        site_id,
        account_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return row


def site_row_to_dict(row, page_count: Optional[int] = None) -> dict:
    """Map a cappe_sites row to the CappeSite response shape."""
    d = dict(row)
    d["theme_config"] = loads(row["theme_config"])
    d["meta_config"] = loads(row["meta_config"])
    if page_count is not None:
        d["page_count"] = page_count
    return d


def page_row_to_dict(row) -> dict:
    """Map a cappe_pages row to the CappePage response shape."""
    d = dict(row)
    d["content"] = loads(row["content"])
    return d
