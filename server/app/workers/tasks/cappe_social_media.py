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

``prepare_cappe_social_export`` makes the files the owner downloads for
Instagram, TikTok and YouTube (`services/social/exports.py`). It does ONE
step per run — probe, listen for the words (Gemini), cut one file, write the
captions file — records it, and queues itself for the next, so the minute
publisher gets the worker between steps. A step that times out or keeps
failing is recorded on that file alone (the export ends `partial`), never the
whole export.

``run_cappe_social_media_sweep`` (every five minutes, the publisher's
single-chain guard) re-queues renders and exports that stalled, clears
uploads that never finished, puts back post targets a killed worker left
`publishing`, and removes video and export files past their expiry.
"""
import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

from app.cappe.services.social import assets as asset_store
from app.cappe.services.social import exports as export_store
from app.cappe.services.social import posts as post_store
from app.cappe.services.social import presets, render, subtitles, transcribe

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
# Gemini busy or not set up: try the words again in five minutes, and give
# up on captions (not the files) after a few tries.
TRANSCRIBE_RETRY_SECONDS = 300
TRANSCRIBE_MAX_RUNS = 6
NO_AUDIO = "That video has no sound, so there are no captions."
NO_WORDS = "We couldn't make out the words clearly enough for captions."
NO_CAPTIONS_NOW = export_store.CAPTIONS_UNAVAILABLE
NO_LIBASS = "Captions aren't available on this server yet, so the files have none."
TRIMMED = "Only the first 3 minutes are in the files."
_EXPORT_FAILURE = "We couldn't make that file. Try preparing the video again."


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
    except SoftTimeLimitExceeded:
        message = "Preparing the video took too long. Try a shorter clip."
    except Exception as exc:  # noqa: BLE001
        logger.warning("cappe social video: render of %s failed: %s", asset_id, exc, exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=120)
        message = str(exc) if isinstance(exc, render.RenderError) else _GENERIC_FAILURE
    asyncio.run(fail_asset(asset_id, message))
    return {"status": "failed", "error": message}


# ── exports: one step per run ───────────────────────────────────────────────

def _facts(export: dict) -> render.VideoFacts:
    f = export.get("facts") or {}
    return render.VideoFacts(duration_ms=int(f.get("duration_ms") or 0), width=int(f.get("width") or 0),
                             height=int(f.get("height") or 0), has_audio=bool(f.get("has_audio")), codec="")


async def _listen(conn, export: dict, asset: dict, source: str, facts: render.VideoFacts, work: Path) -> Optional[int]:
    """The clip's words, kept on the video. Returns a delay when Gemini
    said not now. A video with no sound, or whose words can't be made out,
    keeps that for good; Gemini busy, missing or failing is noted on this
    export only, so a later one tries again."""
    if not facts.has_audio:
        await asset_store.record_transcript(conn, asset["id"], {"words": [], "reason": "no_audio"})
        await export_store.add_warning(conn, export["id"], NO_AUDIO)
        return None
    if not transcribe.configured():
        # Not a passing state: the files don't wait on a key nobody set.
        logger.info("cappe social export %s: no Gemini key on this server; files without captions", export["id"])
        await export_store.add_warning(conn, export["id"], NO_CAPTIONS_NOW)
        return None
    try:
        audio = await transcribe.extract_audio(source, work, max_seconds=presets.MAX_EXPORT_SECONDS)
        heard = await transcribe.transcribe(audio)
    except transcribe.TranscribeUnavailable as exc:
        if int(export.get("attempts") or 0) < TRANSCRIBE_MAX_RUNS:
            logger.info("cappe social export %s: %s; trying again later", export["id"], exc)
            return TRANSCRIBE_RETRY_SECONDS
        await export_store.add_warning(conn, export["id"], NO_CAPTIONS_NOW)
        await asset_store.record_transcript(conn, asset["id"], {"words": [], "reason": "unavailable"})
        return None
    except transcribe.TranscribeError as exc:
        logger.warning("cappe social export %s: no captions: %s", export["id"], exc)
        await export_store.add_warning(conn, export["id"], NO_CAPTIONS_NOW)
        await asset_store.record_transcript(conn, asset["id"], {"words": [], "reason": "failed"})
        return None
    if not heard.words:
        await asset_store.record_transcript(conn, asset["id"], {"words": [], "reason": "no_timings"})
        await export_store.add_warning(conn, export["id"], NO_WORDS)
        return None
    await asset_store.record_transcript(conn, asset["id"], {
        "words": subtitles.compact(heard.words), "text": heard.text, "language": heard.language})
    return None


async def _cut_for_export(conn, export: dict, asset: dict, source: str, facts: render.VideoFacts, key: str,
                          work: Path) -> None:
    recipe = presets.Recipe.from_key(key)
    words = subtitles.expand((asset.get("transcript") or {}).get("words"))
    burn = recipe.captions and bool(words)
    if burn and not render.has_filter("ass"):
        await export_store.add_warning(conn, export["id"], NO_LIBASS)
        burn = False
    plain = recipe if burn or not recipe.captions else presets.Recipe(recipe.spec, False, recipe.max_seconds)
    reused = presets.reusable_render(plain, asset)
    if reused:
        await export_store.record_output(conn, export["id"], key, reused)
        return
    captions_path = fonts = None
    if burn:
        lines = subtitles.group(words, max_chars=recipe.box.max_chars, max_words=recipe.box.max_words)
        path = work / "captions.ass"
        path.write_text(subtitles.ass_document(lines, width=recipe.spec.width, height=recipe.spec.height,
                                               box=recipe.box), encoding="utf-8")
        captions_path = str(path)
        fonts = presets.FONTS_DIR if os.path.isdir(presets.FONTS_DIR) else None
    out = await render.encode(source, recipe.spec, facts, work, name=key, max_seconds=recipe.max_seconds,
                              max_bytes=presets.EXPORT_MAX_BYTES, subtitles=captions_path, fonts_dir=fonts,
                              timeout=presets.EXPORT_ENCODE_TIMEOUT)
    stored = await asset_store.upload_render(str(out), asset["id"], key)
    out.unlink(missing_ok=True)
    await export_store.record_output(conn, export["id"], key, {
        **stored, "width": recipe.spec.width, "height": recipe.spec.height,
        "duration_ms": int(render.clip_seconds(facts, recipe.max_seconds) * 1000),
        "trimmed": facts.duration_ms > recipe.max_seconds * 1000, "shared": False,
    })


async def _write_srt(conn, export: dict, asset: dict, work: Path) -> None:
    words = subtitles.expand((asset.get("transcript") or {}).get("words"))
    path = work / "captions.srt"
    path.write_text(subtitles.srt_document(subtitles.srt_lines(words)), encoding="utf-8")
    stored = await asset_store.upload_text(str(path), asset["id"], "captions", ".srt", "application/x-subrip")
    await export_store.record_srt(conn, export["id"], stored)


async def _run_step(conn, export: dict, asset: dict, step: export_store.Step) -> Optional[int]:
    source = asset_store.source_read_url(asset["source_path"])
    if step.kind == "probe":
        facts = await render.probe(source)
        await export_store.record_facts(conn, export["id"], facts,
                                        presets.targets_for(export["platforms"], facts, captions=export["captions"]))
        if facts.duration_ms > presets.MAX_EXPORT_SECONDS * 1000:
            await export_store.add_warning(conn, export["id"], TRIMMED)
        return None
    facts = _facts(export)
    with tempfile.TemporaryDirectory(prefix="cappe-export-") as tmp:
        work = Path(tmp)
        if step.kind == "transcribe":
            return await _listen(conn, export, asset, source, facts, work)
        if step.kind == "encode":
            await _cut_for_export(conn, export, asset, source, facts, step.recipe or "", work)
        elif step.kind == "srt":
            await _write_srt(conn, export, asset, work)
    return None


async def _give_up_step(conn, export: dict, step: Optional[dict], message: str) -> bool:
    """Record a failed step on its own file so the rest goes on. Returns
    False when the export as a whole is over."""
    kind = (step or {}).get("kind")
    if kind == "encode" and step.get("recipe"):
        await export_store.record_output(conn, export["id"], step["recipe"], {"error": message})
    elif kind == "transcribe":
        await asset_store.record_transcript(conn, export["asset_id"], {"words": [], "reason": "failed"})
        await export_store.add_warning(conn, export["id"], NO_CAPTIONS_NOW)
    elif kind == "srt":
        await export_store.record_srt(conn, export["id"], {"error": message})
    else:
        await export_store.finish(conn, export["id"], "failed", message)
        return False
    await export_store.set_step(conn, export["id"], None)
    await export_store.requeue(conn, export["id"])
    return True


async def prepare_step(export_id: str) -> dict:
    """One step of one export. `next` is None when there is nothing more,
    else the delay (seconds) before the next run."""
    conn = await get_db_connection()
    try:
        export = await export_store.claim(conn, UUID(export_id))
        if export is None:
            return {"skipped": True, "next": None}
        if int(export["attempts"]) > export_store.MAX_RUNS:
            await export_store.finish(conn, export["id"], export_store.rollup(export),
                                      "Preparing kept getting interrupted. Try again.")
            return {"gave_up": True, "next": None}
        asset = await asset_store.get_by_id(conn, export["asset_id"])
        if asset is None or asset["status"] in ("failed", "deleted"):
            await export_store.finish(conn, export["id"], "failed", (asset or {}).get("error") or "The video is gone.")
            return {"failed": True, "next": None}
        step = export_store.next_step(export, asset)
        if step.kind == "done":
            status = export_store.rollup(export)
            await export_store.finish(conn, export["id"], status,
                                      "None of the files could be made." if status == "failed" else None)
            return {"done": status, "next": None}
        await export_store.set_step(conn, export["id"], step)
        try:
            wait = await _run_step(conn, export, asset, step)
        except render.RenderError as exc:
            if not exc.permanent:
                raise
            go_on = await _give_up_step(conn, export, step.as_json(), str(exc))
            return {"step": step.kind, "error": str(exc), "next": 0 if go_on else None}
        except asset_store.AssetStorageUnavailable as exc:
            await export_store.finish(conn, export["id"], "failed", str(exc))
            return {"failed": True, "next": None}
        await export_store.set_step(conn, export["id"], None)
        await export_store.requeue(conn, export["id"])
        return {"step": step.kind, "recipe": step.recipe, "next": wait or 0}
    finally:
        await conn.close()


async def abandon_step(export_id: str, message: str) -> bool:
    """After a timeout or a second failure: give up on the step that was
    running. Returns whether the export goes on."""
    conn = await get_db_connection()
    try:
        export = await export_store.get_by_id(conn, UUID(export_id))
        if export is None or export["status"] not in export_store.OPEN:
            return False
        return await _give_up_step(conn, export, export.get("step"), message)
    finally:
        await conn.close()


def _queue_export(export_id: str, countdown: Optional[int]) -> None:
    if countdown is None:
        return
    try:
        if countdown:
            prepare_cappe_social_export.apply_async(args=[export_id], countdown=countdown)
        else:
            prepare_cappe_social_export.delay(export_id)
    except Exception:  # noqa: BLE001 — the sweep picks up an export nobody is working on
        logger.warning("cappe social export: could not queue the next step of %s; the sweep will", export_id,
                       exc_info=True)


@celery_app.task(bind=True, max_retries=1, soft_time_limit=540, time_limit=590)
def prepare_cappe_social_export(self, export_id: str) -> dict:
    """One step of an export, then the next is queued. A step that fails
    twice or runs out of time is given up on its own."""
    try:
        result = asyncio.run(prepare_step(export_id))
        _queue_export(export_id, result.get("next"))
        return {"status": "success", **result}
    except SoftTimeLimitExceeded:
        message = "Making that file took too long. Try a shorter clip."
    except Exception as exc:  # noqa: BLE001
        logger.warning("cappe social export: a step of %s failed: %s", export_id, exc, exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=120)
        message = str(exc) if isinstance(exc, render.RenderError) else _EXPORT_FAILURE
    go_on = asyncio.run(abandon_step(export_id, message))
    _queue_export(export_id, 0 if go_on else None)
    return {"status": "step_failed", "error": message}


def queue_exports(export_ids: list) -> None:
    """Start exports a route just created (after its transaction)."""
    for export_id in export_ids:
        _queue_export(str(export_id), 0)


# ── the sweep ───────────────────────────────────────────────────────────────

async def sweep(conn, limit: int) -> dict:
    """One pass over everything that can get stuck. Pure orchestration over
    the stores, so it is testable with a fake connection."""
    out = {"renders_requeued": 0, "renders_failed": 0, "uploads_cleared": 0, "targets_recovered": 0, "expired": 0,
           "exports_requeued": 0, "exports_failed": 0, "exports_expired": 0}
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
    stalled: list[str] = []
    for export in await export_store.stuck(conn, minutes=STUCK_RENDER_MINUTES, limit=limit):
        if int(export.get("attempts") or 0) >= export_store.MAX_RUNS:
            await export_store.finish(conn, export["id"], export_store.rollup(export),
                                      "Preparing kept getting interrupted. Try again.")
            out["exports_failed"] += 1
        else:
            await export_store.requeue(conn, export["id"])
            stalled.append(str(export["id"]))
    for export_id in stalled:
        try:
            prepare_cappe_social_export.delay(export_id)
            out["exports_requeued"] += 1
        except Exception:  # noqa: BLE001 — next sweep tries again
            logger.warning("cappe social media sweep: could not re-queue export %s", export_id, exc_info=True)
    for export in await export_store.expired(conn, limit=limit):
        await export_store.delete_files(export)
        await export_store.mark_deleted(conn, export["id"])
        out["exports_expired"] += 1
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
