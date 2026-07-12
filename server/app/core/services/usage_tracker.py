"""Usage-event buffer + periodic flusher — the write side of product analytics.

Every usage surface funnels through `record_event`: the `track_api_usage`
middleware (server-side API calls), the `/usage/beacon` endpoint (browser page
views + Werk desktop session/heartbeat). `record_event` is synchronous and
append-only so a hot request path never waits on the DB; a background task
(`start_usage_flusher`) drains the buffer into `usage_events` every 15s in one
batched insert.

Analytics is droppable by design. Nothing here raises into a caller: a full
buffer drops the event (with a warning), and a failed flush logs and discards
the batch rather than re-queueing (a re-queue loop during a DB outage would
just grow until it OOMs the container).

Company resolution happens here, at flush time, not per request. The JWT carries
only sub/email/role — no company — and the mapping lives in `clients.user_id`.
Resolving it per request would put a DB round-trip on every API call, so instead
we batch-resolve the distinct user_ids of a flush and memoize with a 5-minute
TTL. Negative results are cached too: individual/candidate users have no
`clients` row and would otherwise re-query forever.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ...database import get_connection
from .auth import decode_token

logger = logging.getLogger("matcha.usage")

# Buffered events awaiting flush. Tuples, not dicts — this list can hold
# thousands of entries between flushes.
_buffer: list[dict[str, Any]] = []

# Hard cap. A runaway loop (or a long DB outage with heavy traffic) must not
# grow the buffer without bound — the backend container is memory-tight.
_MAX_BUFFER = 10_000
_dropped_since_last_warning = 0

_FLUSH_INTERVAL_SECONDS = 15

# user_id -> (company_id | None, expires_at monotonic)
_company_cache: dict[str, tuple[Optional[str], float]] = {}
_COMPANY_CACHE_TTL = 300.0

_flush_task: Optional[asyncio.Task] = None


def resolve_token(authorization: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Best-effort (user_id, role) from a bearer header. Pure JWT decode, no DB —
    this runs on every API request. Returns (None, None) for missing/invalid."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None, None
    token = authorization[7:].strip()
    try:
        payload = decode_token(token, expected_type="access")
        if not payload:
            return None, None
        return payload.sub, getattr(payload, "role", None)
    except Exception:
        return None, None


def record_event(
    *,
    surface: str,
    event: str,
    path: str,
    method: Optional[str] = None,
    status: Optional[int] = None,
    duration_ms: Optional[int] = None,
    user_id: Optional[str] = None,
    role: Optional[str] = None,
    visitor_id: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    """Queue one usage event. Sync, never throws, never blocks."""
    global _dropped_since_last_warning
    try:
        if len(_buffer) >= _MAX_BUFFER:
            _dropped_since_last_warning += 1
            if _dropped_since_last_warning % 1000 == 1:
                logger.warning(
                    "usage buffer full (%d); dropped %d events so far",
                    _MAX_BUFFER, _dropped_since_last_warning,
                )
            return
        _buffer.append({
            "occurred_at": occurred_at or datetime.now(timezone.utc),
            "surface": surface,
            "event": event,
            "path": path[:300],
            "method": method,
            "status": status,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "role": role,
            "visitor_id": visitor_id[:64] if visitor_id else None,
            "meta": meta,
        })
    except Exception:
        # Recording usage must never break the caller.
        pass


async def _resolve_companies(user_ids: set[str]) -> dict[str, Optional[str]]:
    """Map user_id -> company_id for a flush batch. Cache-first, one query for
    the misses. Users with several `clients` rows resolve to their earliest
    company, deterministically."""
    now = time.monotonic()
    resolved: dict[str, Optional[str]] = {}
    missing: list[str] = []

    for uid in user_ids:
        hit = _company_cache.get(uid)
        if hit and hit[1] > now:
            resolved[uid] = hit[0]
        else:
            missing.append(uid)

    if not missing:
        return resolved

    try:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (cl.user_id) cl.user_id, cl.company_id
                FROM clients cl
                WHERE cl.user_id = ANY($1::uuid[])
                ORDER BY cl.user_id, cl.created_at
                """,
                missing,
            )
    except Exception:
        logger.warning("usage: company resolution failed", exc_info=True)
        return resolved

    found = {str(r["user_id"]): str(r["company_id"]) if r["company_id"] else None for r in rows}
    expiry = now + _COMPANY_CACHE_TTL
    for uid in missing:
        company_id = found.get(uid)
        resolved[uid] = company_id
        # Cache misses too — individuals/candidates have no clients row and
        # would otherwise re-query on every flush.
        _company_cache[uid] = (company_id, expiry)

    if len(_company_cache) > 5000:
        for k in [k for k, (_, exp) in _company_cache.items() if exp <= now]:
            _company_cache.pop(k, None)

    return resolved


async def flush() -> int:
    """Drain the buffer into usage_events. Returns rows written."""
    if not _buffer:
        return 0

    # Swap the buffer out atomically w.r.t. the event loop — record_event is
    # sync, so no await can interleave between these two statements.
    batch = _buffer[:]
    del _buffer[:]

    try:
        user_ids = {e["user_id"] for e in batch if e.get("user_id")}
        companies = await _resolve_companies(user_ids) if user_ids else {}

        import json as _json

        rows = [
            (
                e["occurred_at"], e["surface"], e["event"], e["path"],
                e["method"], e["status"], e["duration_ms"],
                e["user_id"], companies.get(e["user_id"]) if e.get("user_id") else None,
                e["role"], e["visitor_id"],
                _json.dumps(e["meta"]) if e.get("meta") else None,
            )
            for e in batch
        ]

        async with get_connection() as conn:
            await conn.executemany(
                """
                INSERT INTO usage_events
                    (occurred_at, surface, event, path, method, status, duration_ms,
                     user_id, company_id, role, visitor_id, meta)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::uuid, $9::uuid, $10, $11, $12::jsonb)
                """,
                rows,
            )
        return len(rows)
    except Exception:
        # Drop the batch rather than re-queue: during a DB outage a re-queue
        # loop would grow the buffer until the container dies.
        logger.warning("usage: flush failed, dropped %d events", len(batch), exc_info=True)
        return 0


async def _flush_loop() -> None:
    while True:
        try:
            await asyncio.sleep(_FLUSH_INTERVAL_SECONDS)
            await flush()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("usage: flush loop error", exc_info=True)


def start_usage_flusher() -> None:
    """Start the periodic flusher (per uvicorn worker — each owns its buffer)."""
    global _flush_task
    if _flush_task and not _flush_task.done():
        return
    _flush_task = asyncio.create_task(_flush_loop())


async def stop_usage_flusher() -> None:
    """Cancel the flusher and drain whatever is left, best-effort."""
    global _flush_task
    if _flush_task:
        _flush_task.cancel()
        try:
            await _flush_task
        except (asyncio.CancelledError, Exception):
            pass
        _flush_task = None
    try:
        await flush()
    except Exception:
        pass
