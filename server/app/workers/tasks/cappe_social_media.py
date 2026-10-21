"""Cappe social video: cut a dropped clip to size, and keep the pipeline tidy.

``render_cappe_social_video`` runs once per uploaded clip, on the default
worker (one slot, 768 MB — the owner chose not to stand up a media host
yet). It reads the original from S3 through a presigned URL, takes three
poster frames, then cuts each render one at a time (`services/social/
render.py` bounds every ffmpeg) and uploads it before the next starts. It is
idempotent: frames and renders already stored are skipped, so a run killed by
the hourly worker restart resumes where it stopped. When the clip is ready,
the posts waiting on it go back to `scheduled`, and any already due are
published right away. A clip that can't be used fails with a reason the
owner sees, and so do the posts waiting on it.

``run_cappe_social_media_sweep`` (every five minutes, the publisher's
single-chain guard) re-queues renders that stalled, clears uploads that never
finished, puts back post targets a killed worker left `publishing`, and
removes video files past their expiry that no live post needs.
"""
import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

from app.cappe.services.social import assets as asset_store
from app.cappe.services.social import posts as post_store
from app.cappe.services.social import render

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled, scheduler_settings_row

logger = logging.getLogger(__name__)

TASK_KEY = "cappe_social_media_sweep"
SWEEP_SECONDS = 300
MIN_GAP = 240
STUCK_RENDER_MINUTES = 30
STALE_CLAIM_MINUTES = 20
MAX_RENDER_ATTEMPTS = 2
_GENERIC_FAILURE = "We couldn't prepare that video. Try uploading it again."


async def _fail(conn, asset_id: UUID, message: str) -> list[UUID]:
    await asset_store.mark_failed(conn, asset_id, message)
    return await post_store.fail_rendering(conn, asset_id, message)


async def _cut(conn, asset: dict) -> None:
    """Probe, frames, renders — each stored as soon as it exists."""
    source = asset_store.source_read_url(asset["source_path"])
    with tempfile.TemporaryDirectory(prefix="cappe-video-") as tmp:
        work = Path(tmp)
        facts = await render.probe(source)
        await asset_store.record_facts(conn, asset["id"], facts)
        if not asset["frames"]:
            frames = []
            for index, at_ms in enumerate(render.frame_points_ms(facts)):
                path = await render.extract_frame(source, at_ms, work, index)
                frames.append({"url": await asset_store.upload_frame(str(path), asset["id"], index), "t_ms": at_ms})
                path.unlink(missing_ok=True)
            await asset_store.record_frames(conn, asset["id"], frames)
        for spec in render.specs_for(facts):
            if spec.name in asset["renders"]:
                continue
            path = await render.encode(source, spec, facts, work)
            stored = await asset_store.upload_render(str(path), asset["id"], spec.name)
            path.unlink(missing_ok=True)
            await asset_store.record_render(conn, asset["id"], spec.name, {
                **stored, "width": spec.width, "height": spec.height,
                "duration_ms": int(facts.output_seconds * 1000),
            })


async def render_one(asset_id: str) -> dict:
    """Cut one clip. A file that can't be used fails here; anything else
    (storage, a flaky read) raises for the task to retry once."""
    conn = await get_db_connection()
    try:
        asset = await asset_store.get_by_id(conn, UUID(asset_id))
        if asset is None or asset["status"] != "rendering":
            return {"skipped": True, "reason": asset["status"] if asset else "missing"}
        await asset_store.start_render(conn, asset["id"])
        try:
            await _cut(conn, asset)
        except render.RenderError as exc:
            if not exc.permanent:
                raise
            failed = await _fail(conn, asset["id"], str(exc))
            return {"failed": True, "error": str(exc), "posts_failed": len(failed)}
        except asset_store.AssetStorageUnavailable as exc:
            failed = await _fail(conn, asset["id"], str(exc))
            return {"failed": True, "error": str(exc), "posts_failed": len(failed)}
        await asset_store.mark_ready(conn, asset["id"])
        released = await post_store.release_rendered(conn, asset["id"])
    finally:
        await conn.close()
    now = datetime.now(timezone.utc)
    due = [r["id"] for r in released if r.get("scheduled_at") is not None and r["scheduled_at"] <= now]
    _publish(due)
    return {"ready": True, "posts_released": len(released), "posts_due": len(due)}


def _publish(post_ids: list[UUID]) -> None:
    """Posts whose time already came while the video was being cut go out now
    rather than at the next minute's sweep."""
    if not post_ids:
        return
    try:
        from app.workers.tasks.cappe_social_publisher import run_cappe_social_publish_post

        for post_id in post_ids:
            run_cappe_social_publish_post.delay(str(post_id))
    except Exception:  # noqa: BLE001 — the minute sweep publishes them anyway
        logger.warning("cappe social video: could not dispatch publishing; the sweep will", exc_info=True)


async def fail_asset(asset_id: str, message: str) -> None:
    conn = await get_db_connection()
    try:
        await _fail(conn, UUID(asset_id), message)
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1, soft_time_limit=560, time_limit=590)
def render_cappe_social_video(self, asset_id: str) -> dict:
    """Cut one dropped clip for every network. Retried once for a passing
    failure; after that the clip (and the posts on it) fail with a reason."""
    try:
        return {"status": "success", **asyncio.run(render_one(asset_id))}
    except SoftTimeLimitExceeded as exc:
        # The render resumes where it stopped (frames and cuts already stored
        # are skipped), so running out of time once is worth one more run.
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30)
        message = "Preparing the video took too long. Try a shorter clip."
    except Exception as exc:  # noqa: BLE001
        logger.warning("cappe social video: render of %s failed: %s", asset_id, exc, exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=120)
        message = str(exc) if isinstance(exc, render.RenderError) else _GENERIC_FAILURE
    asyncio.run(fail_asset(asset_id, message))
    return {"status": "failed", "error": message}


# ── the sweep ───────────────────────────────────────────────────────────────

async def sweep(conn, limit: int) -> dict:
    """One pass over everything that can get stuck. Pure orchestration over
    the stores, so it is testable with a fake connection."""
    out = {"renders_requeued": 0, "renders_failed": 0, "uploads_cleared": 0, "targets_recovered": 0, "expired": 0,
           "posts_released": 0, "posts_failed": 0}
    requeue: list[str] = []
    for asset in await asset_store.stuck_renders(conn, minutes=STUCK_RENDER_MINUTES, limit=limit):
        if int(asset.get("render_attempts") or 0) >= MAX_RENDER_ATTEMPTS:
            await _fail(conn, asset["id"], "Preparing the video kept getting interrupted. Try uploading it again.")
            out["renders_failed"] += 1
        else:
            await asset_store.touch_render(conn, asset["id"])
            requeue.append(str(asset["id"]))
    for asset_id in requeue:
        try:
            render_cappe_social_video.delay(asset_id)
            out["renders_requeued"] += 1
        except Exception:  # noqa: BLE001 — next sweep tries again
            logger.warning("cappe social media sweep: could not re-queue %s", asset_id, exc_info=True)
    for asset in await asset_store.take_abandoned_uploads(conn, limit=limit):
        await asset_store.delete_files(asset)
        out["uploads_cleared"] += 1
    for post_id in await post_store.recover_stale_claims(conn, STALE_CLAIM_MINUTES):
        await post_store.rollup_post(conn, post_id)
        out["targets_recovered"] += 1
    settled = await post_store.settle_renders(conn, limit=limit)
    out["posts_released"], out["posts_failed"] = len(settled["released"]), len(settled["failed"])
    now = datetime.now(timezone.utc)
    _publish([r["id"] for r in settled["released"] if r.get("scheduled_at") is not None and r["scheduled_at"] <= now])
    for asset in await asset_store.expired(conn, limit=limit):
        await asset_store.delete_files(asset)
        await asset_store.mark_deleted(conn, asset["id"])
        out["expired"] += 1
    return out


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
        settings = await scheduler_settings_row(conn, TASK_KEY)
        limit = max(1, min(int((settings["max_per_cycle"] if settings else None) or 50), 500))
        return {**await sweep(conn, limit), "reschedule": True}
    finally:
        await conn.close()


def _reschedule(countdown: int) -> None:
    try:
        run_cappe_social_media_sweep.apply_async(countdown=countdown)
    except Exception:  # noqa: BLE001 — the next hourly restart starts the chain again
        logger.exception("cappe social media sweep: could not re-enqueue")


@celery_app.task(bind=True, max_retries=1)
def run_cappe_social_media_sweep(self) -> dict:
    """Recover stuck video renders and publishes; remove expired video files.
    Re-enqueues every five minutes while enabled."""
    try:
        result = asyncio.run(_run_sweep())
    except Exception as exc:
        logger.exception("Cappe social media sweep failed")
        raise self.retry(exc=exc, countdown=60)
    if result.get("reschedule"):
        _reschedule(SWEEP_SECONDS)
    return {"status": "success", **result}
