"""Publish due Cappe social posts, swept every minute.

The worker has no beat: periodic tasks are dispatched once per hourly restart
(``celery_app.on_worker_ready``). A post scheduled for 9:00 has to go out at
9:00, so this task re-enqueues itself ``SWEEP_SECONDS`` out after every run,
with the same single-chain guard ``schedule_break_reminders`` uses: each run
claims ``scheduler_settings.last_run_at`` and a run that finds a claim younger
than ``MIN_GAP`` ends without re-enqueueing, so the extra chain a restart
starts dies out. Correctness never rests on it — targets are claimed with
``FOR UPDATE SKIP LOCKED`` — it only keeps the cadence single.

"Publish now" from the dashboard dispatches ``run_cappe_social_publish_post``
for one post instead of waiting for the sweep.
"""
import asyncio
import logging

from app.cappe.services.social import outbound
from app.cappe.services.social import posts as post_store
from app.cappe.services.social.providers.meta import MetaConfig

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled, scheduler_settings_row

logger = logging.getLogger(__name__)

TASK_KEY = "cappe_social_publisher"
SWEEP_SECONDS = 60
MIN_GAP = 45


async def publish_claimed(conn, cfg: MetaConfig, claims: list[dict]) -> dict:
    """Publish each claimed target, one transaction's worth of outcome each."""
    counts = {"published": 0, "pending": 0, "failed": 0}
    for claim in claims:
        ended = await outbound.publish_target(conn, cfg, claim)
        counts[ended] = counts.get(ended, 0) + 1
    return counts


async def _run_sweep() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, TASK_KEY, default=False):
            return {"skipped": True, "reason": "disabled", "reschedule": False}
        claimed_slot = await conn.fetchval(
            """UPDATE scheduler_settings SET last_run_at = NOW()
               WHERE task_key = $1
                 AND (last_run_at IS NULL OR last_run_at < NOW() - make_interval(secs => $2))
               RETURNING true""",
            TASK_KEY, MIN_GAP,
        )
        if not claimed_slot:
            return {"skipped": True, "reason": "another_chain", "reschedule": False}
        cfg = MetaConfig.from_settings()
        if cfg is None:
            return {"skipped": True, "reason": "meta_not_configured", "reschedule": True}
        settings = await scheduler_settings_row(conn, TASK_KEY)
        limit = max(1, min(int((settings["max_per_cycle"] if settings else None) or 50), 500))
        async with conn.transaction():
            claims = await post_store.claim_due_targets(conn, limit)
        counts = await publish_claimed(conn, cfg, claims) if claims else {}
        return {"claimed": len(claims), **counts, "reschedule": True}
    finally:
        await conn.close()


def _reschedule(countdown: int) -> None:
    try:
        run_cappe_social_publisher.apply_async(countdown=countdown)
    except Exception:  # noqa: BLE001 — the next hourly restart starts the chain again
        logger.exception("cappe social publisher: could not re-enqueue")


@celery_app.task(bind=True, max_retries=1)
def run_cappe_social_publisher(self) -> dict:
    """Sweep due social post targets; re-enqueue in a minute while enabled."""
    try:
        result = asyncio.run(_run_sweep())
    except Exception as exc:
        logger.exception("Cappe social publisher failed")
        raise self.retry(exc=exc, countdown=60)
    if result.get("reschedule"):
        _reschedule(SWEEP_SECONDS)
    return {"status": "success", **result}


async def _run_one(post_id: str) -> dict:
    conn = await get_db_connection()
    try:
        cfg = MetaConfig.from_settings()
        if cfg is None:
            return {"skipped": True, "reason": "meta_not_configured"}
        async with conn.transaction():
            claims = await post_store.claim_due_targets(conn, 20, post_id=post_id)
        counts = await publish_claimed(conn, cfg, claims) if claims else {}
        return {"claimed": len(claims), **counts}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=2)
def run_cappe_social_publish_post(self, post_id: str) -> dict:
    """Publish one post's due targets right away ("Post now")."""
    try:
        return {"status": "success", **asyncio.run(_run_one(post_id))}
    except Exception as exc:
        logger.exception("Cappe social publish-now failed for %s", post_id)
        raise self.retry(exc=exc, countdown=30)
