"""Image asset library (`cappe_assets`, migration zzzzcappe23).

A per-site catalog over image URLs the account has already generated or
uploaded — nothing here touches storage. Recording a row is deliberately
best-effort everywhere it's called from (`record()` swallows its own
failures via the caller, not here — see routes/uploads.py and merlin.py):
a broken catalog insert must never turn a successful generation/upload into
a user-facing failure.
"""
import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


async def record(
    conn,
    *,
    account_id: UUID,
    site_id: UUID,
    kind: str,
    url: str,
    prompt: Optional[str] = None,
    aspect: Optional[str] = None,
    image_size: Optional[str] = None,
) -> None:
    """Insert one catalog row. Callers wrap this in try/except — see the
    module docstring; asset bookkeeping is never allowed to fail the request
    it's attached to."""
    await conn.execute(
        """
        INSERT INTO cappe_assets (account_id, site_id, kind, url, prompt, aspect, image_size)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        account_id, site_id, kind, url, prompt, aspect, image_size,
    )


async def list_assets(
    conn, site_id: UUID, *, kind: Optional[str] = None, limit: int = 200
) -> list[dict[str, Any]]:
    """A site's assets, newest first. `kind` optionally filters to
    'generated' or 'upload'."""
    if kind:
        rows = await conn.fetch(
            """
            SELECT id, kind, url, prompt, aspect, image_size, created_at
            FROM cappe_assets
            WHERE site_id = $1 AND kind = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            site_id, kind, limit,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, kind, url, prompt, aspect, image_size, created_at
            FROM cappe_assets
            WHERE site_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            site_id, limit,
        )
    return [dict(r) for r in rows]


async def delete_asset(conn, site_id: UUID, asset_id: UUID) -> bool:
    """Delete the catalog row only — never the underlying S3 object, which a
    live page's `_design.bg.image` or a block image field may still
    reference. Returns False if no matching row existed (site-scoped, so a
    foreign asset id 404s rather than deleting cross-tenant)."""
    result = await conn.execute(
        "DELETE FROM cappe_assets WHERE id = $1 AND site_id = $2", asset_id, site_id
    )
    return result != "DELETE 0"
