"""The magazine Library's open imagery (cappemag03): search the archives,
import what the owner picks, follow the imports, "stock a topic".

Searching is a network call to the archive, made with no connection held;
results are cached an hour for everyone (`services/magazine/sources`). An
import is queued here and worked by `workers/tasks/cappe_media_import.py`,
which re-checks the license at the source before downloading anything. The
daily allowance is per account, counted in the database, from the plan's
`stock_imports_per_day` feature.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeStockImportRequest,
    CappeStockImports,
    CappeStockSearch,
    CappeStockTopicRequest,
)
from ..services.entitlements import resolve_entitlements
from ..services.magazine import imports, sources
from ..services.magazine.sources.thumbs import thumb_path
from ..services.magazine.topics import TOPIC_QUERIES
from ._shared import get_owned_site

logger = logging.getLogger(__name__)

router = APIRouter()

SEARCH_PER_HOUR = 120
SOURCE_DOWN = "That archive didn't answer. Try again in a moment, or search another one."


def _dispatch(site_id: UUID) -> None:
    """Start the import worker. Best effort: the owner's polling re-dispatches."""
    try:
        from ...workers.tasks.cappe_media_import import run_cappe_media_import

        run_cappe_media_import.delay(str(site_id))
    except Exception as exc:  # noqa: BLE001 — broker down: the next poll retries
        logger.warning("cappe media import dispatch failed for %s: %s", site_id, exc)


async def _imported(conn, site_id: UUID, keys: list[tuple[str, str]]) -> set[tuple[str, str]]:
    if not keys:
        return set()
    rows = await conn.fetch(
        "SELECT source, source_id FROM cappe_assets WHERE site_id = $1 AND source_id IS NOT NULL "
        "AND (source, source_id) IN (SELECT * FROM unnest($2::text[], $3::text[]))",
        site_id, [k[0] for k in keys], [k[1] for k in keys],
    )
    return {(r["source"], r["source_id"]) for r in rows}


@router.get("/sites/{site_id}/library/search", response_model=CappeStockSearch)
async def search_stock(
    site_id: UUID,
    source: str = Query(..., pattern="^(openverse|smithsonian|met|nasa)$"),
    q: str = Query(..., min_length=1, max_length=sources.MAX_QUERY),
    page: int = Query(0, ge=0, le=sources.MAX_PAGE),
    account: CappeAccount = Depends(require_cappe_account),
):
    """One page of an archive's pictures for `q`, already filtered to licenses
    a magazine can publish."""
    await check_rate_limit(str(account.id), "cappe_stock_search", SEARCH_PER_HOUR, 3600)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
    try:
        results = await sources.search(source, q, page)
    except sources.SourceError as exc:
        logger.info("stock search %s failed: %s", source, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=SOURCE_DOWN) from exc
    async with get_connection() as conn:
        done = await _imported(conn, site_id, [(r.source, r.source_id) for r in results])
    return {
        "source": source, "query": q, "page": page, "has_more": bool(results) and page < sources.MAX_PAGE,
        "results": [{**r.to_dict(), "thumb": thumb_path(r.thumb_url), "imported": (r.source, r.source_id) in done}
                    for r in results],
    }


async def _queue(account: CappeAccount, site_id: UUID, keys: list[tuple[str, str]],
                 post_id: Optional[UUID]) -> dict:
    keys = list(dict.fromkeys(keys))[:imports.MAX_PER_REQUEST]
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        if post_id and not await conn.fetchval("SELECT 1 FROM cappe_posts WHERE id = $1 AND site_id = $2",
                                                post_id, site_id):
            raise HTTPException(status_code=422, detail="That story isn't this site's.")
        ent = await resolve_entitlements(account.plan, conn=conn)
        raw = ent.features.get("stock_imports_per_day")
        allowance = int(raw) if isinstance(raw, int) and not isinstance(raw, bool) else imports.DEFAULT_DAILY
        used = await imports.daily_used(conn, account.id)
        have = await imports.existing(conn, site_id, keys)
        new = [k for k in keys if k not in have or imports.requeueable(have[k])]
        if used + len(new) > allowance:
            left = max(0, allowance - used)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"You can import {left} more picture{'s' if left != 1 else ''} today (your plan allows "
                       f"{allowance} a day).",
            )
        rows = await imports.enqueue(conn, site_id=site_id, account_id=account.id, keys=keys, post_id=post_id)
    if any(r["status"] == "pending" for r in rows):
        _dispatch(site_id)
    return {"imports": [{**r, "asset": None} for r in rows], "remaining_today": max(0, allowance - used - len(new))}


@router.post("/sites/{site_id}/library/import", response_model=CappeStockImports,
             status_code=status.HTTP_202_ACCEPTED)
async def import_stock(site_id: UUID, body: CappeStockImportRequest,
                       account: CappeAccount = Depends(require_cappe_account)):
    """Queue pictures the owner picked from a search. Already-imported ones
    come back as they stand."""
    return await _queue(account, site_id, [(i.source, i.source_id) for i in body.items], body.post_id)


@router.get("/sites/{site_id}/library/imports", response_model=CappeStockImports)
async def import_status(site_id: UUID, ids: str = Query(..., max_length=24 * 37),
                        account: CappeAccount = Depends(require_cappe_account)):
    """Where the owner's imports stand, each with its library picture once in.
    Re-dispatches the worker when an import has been left waiting."""
    try:
        wanted = [UUID(i) for i in ids.split(",") if i.strip()][:imports.MAX_PER_REQUEST]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Bad import id") from exc
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await imports.statuses(conn, site_id, wanted)
        stuck = await imports.stuck(conn, site_id) if any(r["status"] in ("pending", "working") for r in rows) else False
    if stuck:
        _dispatch(site_id)
    return {"imports": rows}


@router.post("/sites/{site_id}/library/stock-topic", response_model=CappeStockImports,
             status_code=status.HTTP_202_ACCEPTED)
async def stock_topic(site_id: UUID, body: CappeStockTopicRequest,
                      account: CappeAccount = Depends(require_cappe_account)):
    """Fill the library with pictures for a topic: a few set searches, in
    order, until `count` pictures not already in the library are found."""
    queries = TOPIC_QUERIES.get(body.topic)
    if not queries:
        raise HTTPException(status_code=422, detail="Pick a topic from the list.")
    await check_rate_limit(str(account.id), "cappe_stock_search", SEARCH_PER_HOUR, 3600)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
    picked: list[tuple[str, str]] = []
    for source, query in queries:
        try:
            results = await sources.search(source, query, 0)
        except sources.SourceError:
            continue
        picked += [(r.source, r.source_id) for r in results]
        if len(picked) >= body.count * 2:
            break
    async with get_connection() as conn:
        done = await _imported(conn, site_id, picked)
    keys = [k for k in dict.fromkeys(picked) if k not in done][:body.count]
    if not keys:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=SOURCE_DOWN)
    return await _queue(account, site_id, keys, body.post_id)
