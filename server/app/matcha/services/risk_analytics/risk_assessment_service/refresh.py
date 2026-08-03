"""Event-driven risk-assessment refresh.

Moved out of `routes/employees/_shared.py` (2026-08-03) so Celery tasks can
import it without pulling in `app.matcha.routes.employees`, which executes
`routes/__init__.py` and loads ~40 routers into the memory-capped worker
(`--max-tasks-per-child=5`) on every ER case mutation.

Runs in either the API process (FastAPI BackgroundTasks) or a Celery worker —
`connection_or_direct` makes every DB call pool-free-safe.
"""
import json
import logging
from dataclasses import asdict as _asdict
from datetime import datetime, timezone
from uuid import UUID

from app.database import connection_or_direct

from . import (
    compute_risk_assessment,
    generate_recommendations,
    load_risk_weights,
    write_risk_history,
)

logger = logging.getLogger(__name__)


async def _consume_risk_refresh_followup(company_id: UUID) -> bool:
    """Delete the NX coalescing lock (the run just finished — don't wait on its
    TTL) and consume the follow-up flag left by `_dispatch_risk_refresh` for any
    edit that arrived while this run was in flight. Best-effort: no redis
    client means no coalescing, so no follow-up semantics either."""
    try:
        from app.core.services.redis_cache import get_redis_cache

        redis = get_redis_cache()
        if redis is None:
            return False
        await redis.delete(f"risk-refresh:{company_id}")
        followup = await redis.get(f"risk-refresh-followup:{company_id}")
        if followup:
            await redis.delete(f"risk-refresh-followup:{company_id}")
            return True
        return False
    except Exception:
        return False


async def refresh_risk_snapshot(company_id: UUID) -> None:
    """Recompute risk assessment snapshot after a wage change or ER case
    mutation, then rerun once more if another mutation coalesced onto the
    Redis lock while this run was in flight (see `_consume_risk_refresh_followup`).
    Bounded to 3 passes so a pathological edit-storm can't loop forever."""
    for _ in range(3):
        await _refresh_risk_assessment_once(company_id)
        if not await _consume_risk_refresh_followup(company_id):
            break


async def _refresh_risk_assessment_once(company_id: UUID) -> None:
    """Single refresh pass.

    Debounced: dimensions are skipped entirely if the last snapshot is under a
    minute old — collapses rapid-fire edits to one recompute, deferring
    (never dropping) the triggering change by sleeping out the remainder of
    the window so the eventual recompute reflects it. The expensive Gemini
    recommendations pass reruns only every 10 minutes even when dimensions do
    refresh, gated on its OWN `recommendations_at` timestamp (not
    `computed_at`, which pass 1 below rewrites every time) — the scheduled
    sweep never runs it at all.
    """
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            "SELECT computed_at, recommendations_at FROM risk_assessment_snapshots WHERE company_id = $1",
            company_id,
        )
    last_computed = row["computed_at"] if row else None
    last_recs = row["recommendations_at"] if row else None

    if last_computed is not None:
        aware_last = last_computed if last_computed.tzinfo else last_computed.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - aware_last).total_seconds()
        if age_seconds < 60:
            import asyncio

            wait = 60 - age_seconds
            logger.info(
                "Risk refresh for company %s deferred %ds — snapshot is %ds old",
                company_id, int(wait), int(age_seconds),
            )
            await asyncio.sleep(wait)

    # Pass 1: save updated dimensions immediately so violations reflect right away
    try:
        async with connection_or_direct() as conn:
            weights = await load_risk_weights(conn)
        result = await compute_risk_assessment(company_id, weights=weights)
        dims_json = json.dumps(
            {k: _asdict(v) for k, v in result.dimensions.items()},
            default=str,
        )
        weights_json = json.dumps(weights)
        async with connection_or_direct() as conn:
            await conn.execute(
                """
                INSERT INTO risk_assessment_snapshots
                    (company_id, overall_score, overall_band, dimensions, weights, computed_at, computed_by)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, NULL)
                ON CONFLICT (company_id) DO UPDATE SET
                    overall_score = EXCLUDED.overall_score,
                    overall_band  = EXCLUDED.overall_band,
                    dimensions    = EXCLUDED.dimensions,
                    weights       = EXCLUDED.weights,
                    computed_at   = EXCLUDED.computed_at,
                    computed_by   = NULL
                """,
                company_id,
                result.overall_score,
                result.overall_band,
                dims_json,
                weights_json,
                result.computed_at,
            )
            # Record in history so trend / anomaly / correlation views see this
            # recompute (the manual + scheduled writers both do this).
            await write_risk_history(
                conn,
                company_id,
                overall_score=result.overall_score,
                overall_band=result.overall_band,
                dims_json=dims_json,
                weights_json=weights_json,
                computed_at=result.computed_at,
                source="auto",
            )
        logger.info("Risk assessment dimensions refreshed for company %s", company_id)
    except Exception:
        logger.exception("Background risk assessment refresh failed for company %s", company_id)
        return

    # Pass 2: update recommendations (best-effort, won't block violation
    # updates). Debounced separately and more loosely than pass 1 — the
    # consulting prose doesn't need to track every edit, just stay fresh.
    if last_recs is not None:
        aware_recs = last_recs if last_recs.tzinfo else last_recs.replace(tzinfo=timezone.utc)
        rec_age = (datetime.now(timezone.utc) - aware_recs).total_seconds()
        if rec_age < 600:
            logger.info("Recommendations refresh for company %s skipped — last run %ds ago", company_id, int(rec_age))
            return
    try:
        from app.config import get_settings
        consultation = await generate_recommendations(result, get_settings())
        async with connection_or_direct() as conn:
            await conn.execute(
                """
                UPDATE risk_assessment_snapshots SET
                    report             = $2,
                    recommendations    = $3::jsonb,
                    recommendations_at = NOW()
                WHERE company_id = $1
                """,
                company_id,
                consultation.get("report"),
                json.dumps(consultation.get("recommendations", []) or [], default=str),
            )
        logger.info("Risk assessment recommendations updated for company %s", company_id)
    except Exception:
        logger.exception("Background risk assessment recommendations failed for company %s (dimensions already saved)", company_id)
