"""Runs a job search as a chain of short worker tasks, one phase each.

No `AGENT_*_QUEUE` is set on prod, so every task shares the single-slot main
worker. A whole search in one task would hold that worker for half an hour; a
chain of short tasks interleaves with everything else.

The chain is held together by the search's `dispatch_token`:

* A task runs only if its token is the search's current one and no other task
  holds the lease (`claim`). A duplicate delivery, a retired chain or a
  cancelled search does nothing.
* Each finished phase writes its outcome under that token and hands the next
  task a NEW token (`advance`), so a late duplicate of an earlier message can
  never start a second chain.
* A chain whose message was lost (a killed worker, a broker hiccup) is
  restarted under a fresh token by `nudge` (whoever polls the status) and by
  `reconcile` (main-worker start). Celery does not redeliver a killed task.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID, uuid4

from app.database import connection_or_direct

from .enqueue import STALE_INTERVAL, dispatch
from .phases import PHASES, Deps, Guard, PhaseFailed, PhaseOutcome
from .service import LIVE, rerank

logger = logging.getLogger(__name__)

# Under Celery's 540s soft limit, with room to write the outcome.
PHASE_SECONDS = 420
LEASE_INTERVAL = "9 minutes"
MAX_ATTEMPTS = 3
RETRY_COUNTDOWN = 30
# A live search with no lease that has not moved in this long lost its task.
IDLE_INTERVAL = "2 minutes"

_LIVE_SQL = ", ".join(f"'{status}'" for status in LIVE)


async def claim(search_id: UUID, token: UUID) -> dict | None:
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"""UPDATE mw_job_searches
                SET lease_until = NOW() + INTERVAL '{LEASE_INTERVAL}',
                    attempts = attempts + 1,
                    status = CASE WHEN status = 'queued' THEN 'planning' ELSE status END,
                    started_at = COALESCE(started_at, NOW()),
                    updated_at = NOW()
                WHERE id = $1 AND dispatch_token = $2 AND deleted_at IS NULL
                  AND status IN ({_LIVE_SQL})
                  AND (lease_until IS NULL OR lease_until < NOW())
                RETURNING *""",
            search_id, token,
        )
    return dict(row) if row else None


async def advance(search_id: UUID, token: UUID, outcome: PhaseOutcome, *,
                  retry: bool = False, error: str | None = None) -> tuple[bool, UUID | None]:
    """Write the phase's outcome if this chain still owns the search.

    Returns (written, token for the next task). `written` is False when the
    chain was retired (cancelled, deleted, or replaced by a restart); the next
    token is None when the search is finished.
    """
    terminal = outcome.status not in LIVE
    next_token = None if terminal else uuid4()
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """UPDATE mw_job_searches
               SET status = $3, dispatch_token = $4, lease_until = NULL,
                   attempts = CASE WHEN $5 THEN attempts ELSE 0 END,
                   progress = progress || $6::jsonb,
                   phase_cursor = COALESCE($7::jsonb, phase_cursor),
                   error = CASE WHEN $8::text IS NULL THEN error ELSE $8 END,
                   completed_at = CASE WHEN $9 THEN NOW() ELSE completed_at END,
                   updated_at = NOW()
               WHERE id = $1 AND dispatch_token = $2
               RETURNING id""",
            search_id, token, outcome.status, next_token, retry,
            json.dumps(outcome.progress or {}),
            json.dumps(outcome.cursor) if outcome.cursor is not None else None,
            error, terminal,
        )
    if row is None:
        return False, None
    return True, next_token


async def _ending(search: dict, message: str) -> PhaseOutcome:
    """A search that cannot go on: `done` (counted) if it has ranked jobs to
    show, else `failed` (free)."""
    async with connection_or_direct() as conn:
        leads = int(await conn.fetchval(
            "SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1", search["id"],
        ) or 0)
        if leads:
            fresh = await conn.fetchrow("SELECT * FROM mw_job_searches WHERE id = $1", search["id"])
            await rerank(conn, fresh)
    if leads:
        return PhaseOutcome(status="done", progress={"note": f"Stopped early: {message}", "ranked": True})
    return PhaseOutcome(status="failed", progress={"note": message})


async def run_phase(search_id: UUID, token: UUID, *, deps: Deps | None = None) -> None:
    search = await claim(search_id, token)
    if search is None:
        return
    deps = deps or Deps()
    guard = Guard(search_id, token)
    phase = PHASES.get(search["status"])
    error = None
    retry = False
    if phase is None:
        outcome = await _ending(search, f"Unknown step {search['status']!r}.")
        error = outcome.progress["note"]
    else:
        try:
            outcome = await asyncio.wait_for(phase(search, deps, guard), PHASE_SECONDS)
        except PhaseFailed as exc:
            outcome = await _ending(search, str(exc))
            error = str(exc)
        except Exception as exc:  # TimeoutError included
            logger.warning("job search phase failed search=%s phase=%s attempt=%s",
                           search_id, search["status"], search["attempts"], exc_info=True)
            if int(search["attempts"]) >= MAX_ATTEMPTS:
                message = "A step kept failing, so the search stopped."
                outcome = await _ending(search, message)
                error = f"{message} ({type(exc).__name__})"
            else:
                outcome = PhaseOutcome(
                    status=search["status"], countdown=RETRY_COUNTDOWN,
                    progress={"note": "Hit a snag; trying that step again shortly…"},
                )
                retry = True
    _written, next_token = await advance(search_id, token, outcome, retry=retry, error=error)
    if next_token is None:
        return
    try:
        await dispatch(search_id, next_token, countdown=outcome.countdown)
    except Exception:
        # The search stays live with no lease; nudge/reconcile restart it.
        logger.exception("job search next phase dispatch failed search=%s", search_id)


async def _restart(search_id: UUID) -> bool:
    """Give an idle live search a new token and dispatch it. True if restarted."""
    token = uuid4()
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"""UPDATE mw_job_searches SET dispatch_token = $2, updated_at = NOW()
                WHERE id = $1 AND deleted_at IS NULL AND status IN ({_LIVE_SQL})
                  AND (lease_until IS NULL OR lease_until < NOW())
                  AND updated_at < NOW() - INTERVAL '{IDLE_INTERVAL}'
                RETURNING id""",
            search_id, token,
        )
    if row is None:
        return False
    try:
        await dispatch(search_id, token)
    except Exception:
        logger.exception("job search restart dispatch failed search=%s", search_id)
        return False
    logger.info("job search restarted search=%s", search_id)
    return True


async def nudge(search_id: UUID) -> bool:
    """Restart this search's chain if it has stalled. Cheap when it hasn't."""
    try:
        return await _restart(search_id)
    except Exception:
        logger.warning("job search nudge failed search=%s", search_id, exc_info=True)
        return False


async def reconcile() -> dict:
    """Main-worker start: end searches dead for hours, restart idle ones."""
    ended = restarted = 0
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""SELECT * FROM mw_job_searches
                WHERE deleted_at IS NULL AND status IN ({_LIVE_SQL})
                  AND (lease_until IS NULL OR lease_until < NOW())
                  AND updated_at < NOW() - INTERVAL '{IDLE_INTERVAL}'
                ORDER BY updated_at LIMIT 200""",
        )
        stale_ids = {
            row["id"] for row in await conn.fetch(
                f"""SELECT id FROM mw_job_searches
                    WHERE deleted_at IS NULL AND status IN ({_LIVE_SQL})
                      AND updated_at < NOW() - INTERVAL '{STALE_INTERVAL}'"""
            )
        }
    for row in rows:
        search = dict(row)
        if search["id"] in stale_ids:
            outcome = await _ending(search, "the search stopped making progress.")
            if search["dispatch_token"] is not None:
                written, _ = await advance(search["id"], search["dispatch_token"], outcome,
                                           error="Stopped: no progress.")
                ended += int(written)
            continue
        if await _restart(search["id"]):
            restarted += 1
    return {"ended": ended, "restarted": restarted}
