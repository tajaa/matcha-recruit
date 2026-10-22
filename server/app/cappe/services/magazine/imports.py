"""Importing archive pictures into a site's library (`cappe_asset_imports`,
cappemag03).

The route queues rows (`enqueue`) and dispatches the worker
(`workers/tasks/cappe_media_import.py`), which works them one at a time with
`import_next`:

  1. claim the oldest pending row (or one a dead worker left claimed for over
     ten minutes) in a single statement — `FOR UPDATE SKIP LOCKED`, so two
     runs never take the same picture;
  2. look the picture up again at its archive (`sources.resolve(fresh=True)`):
     the license is re-checked now, not trusted from the search, and anything
     no longer offered under CC0 / public domain / CC BY / CC BY-SA is
     `refused`;
  3. download it through the SSRF-guarded fetcher, re-encode it with its
     responsive sizes (`media.process_image`, which also drops its metadata),
     and upload;
  4. write the library row and mark the import ready together.

No transaction is open, and no row lock held, during any network call. A
download that fails goes back to pending until its third attempt, and is not
claimed again for `RETRY_SECONDS` (a throttled archive isn't asked three times
in a second); the owner's page polls `statuses`, which re-dispatches the
worker for anything stuck, so no scheduled task is needed. A row whose last
attempt died with its worker (the hourly restart) is failed when found, so a
new request can queue it again; it never stays `working`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Iterable, Optional
from uuid import UUID

from ....core.services.safe_fetch import fetch_public
from .. import media
from ..cappe_assets import COLUMNS as ASSET_COLUMNS, row as asset_row
from . import sources
from .sources.base import IMAGE_ACCEPT

logger = logging.getLogger(__name__)

IMPORT_COLS = "id, site_id, source, source_id, status, attempts, error, asset_id, post_id, created_at, updated_at"
MAX_PER_REQUEST = 24
MAX_ATTEMPTS = 3
STUCK_MINUTES = 10
RETRY_SECONDS = 60
DEFAULT_DAILY = 25
MAX_IMAGE_BYTES = 25 * 1024 * 1024
DOWNLOAD_SECONDS = 45

REFUSED = "This picture isn't offered under a license we can publish any more."
UNREADABLE = "That file isn't a picture we can use."
UNREACHABLE = "The archive didn't send the picture. Try importing it again later."


async def daily_used(conn, account_id: UUID) -> int:
    """Imports queued in the last day. A re-queued row counts again: `enqueue`
    moves its `created_at` to the new request."""
    return int(await conn.fetchval(
        "SELECT count(*) FROM cappe_asset_imports WHERE account_id = $1 AND created_at > NOW() - INTERVAL '24 hours'",
        account_id,
    ) or 0)


async def existing(conn, site_id: UUID, keys: Iterable[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    keys = list(keys)
    if not keys:
        return {}
    rows = await conn.fetch(
        f"SELECT {IMPORT_COLS} FROM cappe_asset_imports WHERE site_id = $1 "
        "AND (source, source_id) IN (SELECT * FROM unnest($2::text[], $3::text[]))",
        site_id, [k[0] for k in keys], [k[1] for k in keys],
    )
    return {(r["source"], r["source_id"]): dict(r) for r in rows}


def requeueable(row: dict) -> bool:
    """An import a new request starts again: it failed, or its picture was
    imported and then deleted from the library (`asset_id` is set null)."""
    return row["status"] == "failed" or (row["status"] == "ready" and row["asset_id"] is None)


async def enqueue(conn, *, site_id: UUID, account_id: UUID, keys: list[tuple[str, str]],
                  post_id: Optional[UUID] = None) -> list[dict]:
    """Queue imports. A picture already in the library (or on its way) is
    returned as it stands; one that failed, or was deleted from the library, is
    queued again; one refused stays refused."""
    rows = await conn.fetch(
        f"""
        INSERT INTO cappe_asset_imports (site_id, account_id, source, source_id, post_id)
        SELECT $1, $2, s, i, $5 FROM unnest($3::text[], $4::text[]) AS t(s, i)
        ON CONFLICT (site_id, source, source_id) DO UPDATE
            SET status = 'pending', attempts = 0, error = NULL, claimed_at = NULL, updated_at = NOW(),
                created_at = NOW()
            WHERE cappe_asset_imports.status = 'failed'
               OR (cappe_asset_imports.status = 'ready' AND cappe_asset_imports.asset_id IS NULL)
        RETURNING {IMPORT_COLS}
        """,
        site_id, account_id, [k[0] for k in keys], [k[1] for k in keys], post_id,
    )
    queued = {(r["source"], r["source_id"]): dict(r) for r in rows}
    missing = [k for k in keys if k not in queued]
    queued.update(await existing(conn, site_id, missing))
    return [queued[k] for k in keys if k in queued]


async def statuses(conn, site_id: UUID, ids: list[UUID]) -> list[dict]:
    """Imports by id, each with its library picture once ready."""
    rows = await conn.fetch(
        f"SELECT {IMPORT_COLS} FROM cappe_asset_imports WHERE site_id = $1 AND id = ANY($2::uuid[]) "
        "ORDER BY created_at",
        site_id, ids,
    )
    out = [dict(r) for r in rows]
    asset_ids = [r["asset_id"] for r in out if r["asset_id"]]
    assets: dict[str, dict] = {}
    if asset_ids:
        found = await conn.fetch(
            f"SELECT {ASSET_COLUMNS} FROM cappe_assets WHERE site_id = $1 AND id = ANY($2::uuid[])",
            site_id, asset_ids,
        )
        assets = {str(a["id"]): asset_row(a) for a in found}
    for r in out:
        r["asset"] = assets.get(str(r["asset_id"])) if r["asset_id"] else None
    return out


async def stuck(conn, site_id: UUID) -> bool:
    """Imports left waiting: never claimed, or claimed by a worker that died."""
    return bool(await conn.fetchval(
        "SELECT 1 FROM cappe_asset_imports WHERE site_id = $1 AND attempts < $2 AND ("
        f"(status = 'pending' AND updated_at < NOW() - INTERVAL '1 minute') OR "
        f"(status = 'working' AND claimed_at < NOW() - INTERVAL '{STUCK_MINUTES} minutes')) LIMIT 1",
        site_id, MAX_ATTEMPTS,
    ))


# ── the worker's side ────────────────────────────────────────────────────────

async def claim_next(conn, site_id: UUID) -> Optional[dict]:
    # A last attempt whose worker died can't be claimed again: fail it, so a
    # new request for the picture queues it afresh.
    await conn.execute(
        "UPDATE cappe_asset_imports SET status = 'failed', error = $3, updated_at = NOW() "
        f"WHERE site_id = $1 AND status = 'working' AND attempts >= $2 "
        f"AND claimed_at < NOW() - INTERVAL '{STUCK_MINUTES} minutes'",
        site_id, MAX_ATTEMPTS, UNREACHABLE,
    )
    row = await conn.fetchrow(
        f"""
        UPDATE cappe_asset_imports SET status = 'working', attempts = attempts + 1,
               claimed_at = NOW(), updated_at = NOW()
         WHERE id = (SELECT id FROM cappe_asset_imports
                      WHERE site_id = $1 AND attempts < $2
                        AND ((status = 'pending'
                              AND (attempts = 0 OR updated_at < NOW() - INTERVAL '{RETRY_SECONDS} seconds'))
                             OR (status = 'working' AND claimed_at < NOW() - INTERVAL '{STUCK_MINUTES} minutes'))
                      ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
        RETURNING {IMPORT_COLS}, account_id
        """,
        site_id, MAX_ATTEMPTS,
    )
    return dict(row) if row else None


async def _finish(conn, import_id: UUID, status: str, error: Optional[str] = None) -> None:
    await conn.execute(
        "UPDATE cappe_asset_imports SET status = $2, error = $3, updated_at = NOW() WHERE id = $1",
        import_id, status, error,
    )


async def _retry_or_fail(conn, row: dict, error: str) -> str:
    status = "failed" if row["attempts"] >= MAX_ATTEMPTS else "pending"
    await _finish(conn, row["id"], status, error)
    return status


async def _store(conn, row: dict, result: sources.StockResult, stored: media.StoredImage) -> UUID:
    async with conn.transaction():
        asset_id = await conn.fetchval(
            """
            INSERT INTO cappe_assets (account_id, site_id, kind, url, source, source_id, source_url, title, creator,
                                      creator_url, license, license_version, license_url, provider_label, credit_line,
                                      alt, width, height, bytes, mime, variants)
            VALUES ($1, $2, 'stock', $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19,
                    $20::jsonb)
            ON CONFLICT (site_id, source, source_id) WHERE source_id IS NOT NULL DO UPDATE
                SET url = EXCLUDED.url, variants = EXCLUDED.variants, width = EXCLUDED.width,
                    height = EXCLUDED.height, bytes = EXCLUDED.bytes, mime = EXCLUDED.mime, updated_at = NOW()
            RETURNING id
            """,
            row["account_id"], row["site_id"], stored.url, result.source, result.source_id,
            result.landing_url or None, result.title or None, result.creator or None, result.creator_url or None,
            result.license, result.license_version or None, result.license_url or None, result.provider_label or None,
            result.credit_line or None, result.title[:500] or None, stored.width, stored.height,
            stored.bytes, stored.mime, json.dumps(stored.variants),
        )
        await conn.execute(
            "UPDATE cappe_asset_imports SET status = 'ready', error = NULL, asset_id = $2, updated_at = NOW() "
            "WHERE id = $1",
            row["id"], asset_id,
        )
    return asset_id


async def import_one(conn, row: dict) -> str:
    """Work one claimed import; returns the status it ended in."""
    if row["source"] not in sources.SOURCES:
        await _finish(conn, row["id"], "refused", REFUSED)
        return "refused"
    try:
        result = await sources.resolve(row["source"], row["source_id"], fresh=True)
    except sources.SourceError as exc:
        logger.info("stock import %s: resolve failed (%s)", row["id"], exc)
        return await _retry_or_fail(conn, row, UNREACHABLE)
    if result is None:
        await _finish(conn, row["id"], "refused", REFUSED)
        return "refused"
    # The Met's "original" can be a scan of tens of megabytes; its web-large
    # copy (the search thumbnail) is the fallback when that is over the cap.
    # A timeout on the original is a reason to try that copy too.
    urls = [result.image_url] + ([result.thumb_url] if result.source == "met" and result.thumb_url else [])
    fetched = None
    for url in urls:
        try:
            fetched = await fetch_public(url, max_bytes=MAX_IMAGE_BYTES, accept=IMAGE_ACCEPT,
                                         total_timeout=DOWNLOAD_SECONDS)
        except Exception as exc:  # unsafe host, network error, timeout
            logger.info("stock import %s: download failed (%s)", row["id"], type(exc).__name__)
            fetched = None
            continue
        if not fetched.truncated:
            break
    if fetched is None or fetched.status != 200 or fetched.truncated or not fetched.content_type.startswith("image/"):
        return await _retry_or_fail(conn, row, UNREACHABLE)
    mime = fetched.content_type.split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        await _finish(conn, row["id"], "failed", UNREADABLE)
        return "failed"
    try:
        image = await asyncio.to_thread(media.process_image, fetched.body, mime, derivatives=True)
    except media.ImageRejected:
        await _finish(conn, row["id"], "failed", UNREADABLE)
        return "failed"
    try:
        stored = await media.store_processed(image, prefix="cappe/library", filename=f"{row['source']}.jpg")
    except Exception as exc:  # storage hiccup: worth another go
        logger.warning("stock import %s: upload failed (%s)", row["id"], type(exc).__name__)
        return await _retry_or_fail(conn, row, UNREACHABLE)
    await _store(conn, row, result, stored)
    return "ready"


async def import_next(conn, site_id: UUID) -> Optional[str]:
    """Claim and work the next import for a site; None when none is waiting."""
    row = await claim_next(conn, site_id)
    if row is None:
        return None
    try:
        return await import_one(conn, row)
    except Exception:  # an adapter's or the database's surprise: this row only, not the run
        logger.exception("stock import %s failed unexpectedly", row["id"])
        return await _retry_or_fail(conn, row, UNREACHABLE)
