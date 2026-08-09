"""Shared helpers for the Cappe routers."""
from typing import Any, Collection, Optional, Sequence
from uuid import UUID

from fastapi import HTTPException, UploadFile, status

from ..services.commerce import fetch_site_owner as _site_owner  # noqa: F401
from ..services.common import (  # noqa: F401
    RESERVED_SUBDOMAINS,
    loads,
    loads_list,
    safe_subdomain_base,
    slugify,
)
from ..services.options import fetch_option_groups  # noqa: F401

# asyncpg returns JSONB columns as text (no global codec is registered), so
# every JSONB read goes through _loads and every write through json.dumps.

_READ_CHUNK_BYTES = 1024 * 1024  # 1 MiB


async def read_capped(file: UploadFile, max_bytes: int, detail: str) -> bytes:
    """Read an upload in bounded chunks, raising 413 as soon as the running
    total exceeds `max_bytes` — instead of `await file.read()`ing the whole
    body first and checking its size after. Bounds peak memory at roughly
    `max_bytes + one chunk` regardless of how large the actual upload is."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=detail)
        chunks.append(chunk)
    return b"".join(chunks)


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


async def unique_site_slug(conn, table: str, site_id, base: str, column: str = "slug") -> str:
    """Per-site slug uniqueness for tables with UNIQUE(site_id, slug). `table`
    and `column` are caller literals (never user input)."""
    candidate = base
    n = 1
    while await conn.fetchval(
        f"SELECT 1 FROM {table} WHERE site_id = $1 AND {column} = $2", site_id, candidate
    ):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


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


def build_patch(body, cols: Sequence[str], start: int = 0, *, nullable: Optional[Collection[str]] = None) -> tuple[list[str], list[Any]]:
    """Build `col = $n` SET clauses from a partial-update Pydantic model.

    Driven by `model_fields_set` rather than `is not None` — a field the
    caller never sent is left untouched, but an explicit `null` clears a
    nullable column. The `is not None` idiom can't tell those two apart, which
    made several PATCH routes unable to ever clear a nullable field once set.
    `start` offsets placeholder numbering when the caller already bound
    earlier `$1..$start` args before calling this.
    """
    sets: list[str] = []
    args: list[Any] = []
    bad: list[str] = []
    fields = body.model_fields_set
    for col in cols:
        if col in fields:
            value = getattr(body, col)
            if value is None and nullable is not None and col not in nullable:
                bad.append(col)
                continue
            args.append(value)
            sets.append(f"{col} = ${start + len(args)}")
    if bad:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"These fields cannot be null: {', '.join(bad)}")
    return sets, args
