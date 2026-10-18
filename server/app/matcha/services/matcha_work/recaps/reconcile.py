"""Durable queue repair, source completion, expiry and render token fencing."""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import asyncpg

from app.config import get_settings
from app.database import connection_or_direct, decode_jsonb

from . import adapters, observe, settings, storage, storyboard
from app.matcha.models.matcha_work.recaps import Event, Fact, Manifest
from .service import VALID, scrub_steps, tombstone

logger = logging.getLogger(__name__)

# A dispatched render, delivery or cleanup is not dispatched again (and its
# broker message expires) until this lease passes: a busy or absent media
# worker never collects a pile of duplicate messages.
DISPATCH_SECONDS = 600
# Failures a later sweep may not repeat. Anything else fails the recap.
TRANSIENT = (OSError, TimeoutError, asyncpg.PostgresConnectionError, asyncpg.InterfaceError,
             asyncpg.TransactionRollbackError, asyncpg.QueryCanceledError, asyncpg.LockNotAvailableError)
# Off, the sweep only finishes what was already handed to it; it never idles
# on the single main worker.
OUTSTANDING = """SELECT EXISTS (SELECT 1 FROM mw_agent_recap_deliveries
        WHERE state IN ('pending','retry_wait','sending') AND deadline_at IS NOT NULL)
    OR EXISTS (SELECT 1 FROM mw_agent_recap_cleanup_jobs WHERE state='pending' AND not_before<=NOW())"""


async def collect(conn, recap):
    sources = await conn.fetch("SELECT * FROM mw_agent_recap_sources WHERE recap_id=$1 ORDER BY id", recap["id"])
    states = []
    for source in sources:
        state = await observe.refresh_source(conn, source)
        if state == "deleted":
            await tombstone(conn, recap["id"])
            return
        states.append(state)
        await conn.execute("UPDATE mw_agent_recap_sources SET semantic_state=$2 WHERE id=$1", source["id"], state)
    if not states:
        await tombstone(conn, recap["id"])
        return
    if any(state != "terminal" for state in states):
        if recap["created_at"].timestamp() < datetime.now(timezone.utc).timestamp() - 7 * 86400:
            await conn.execute("UPDATE mw_agent_recaps SET state='skipped',last_error_code='waiting_expired' WHERE id=$1", recap["id"])
            await scrub_steps(conn, recap["id"])
        elif recap["state"] in ("collecting", "waiting"):
            await conn.execute("UPDATE mw_agent_recaps SET state=$2 WHERE id=$1", recap["id"], "waiting" if "waiting" in states else "collecting")
        return
    if recap["source_completed_at"] is None:
        await conn.execute(
            """UPDATE mw_agent_recaps SET source_completed_at=NOW(),finalize_after=NOW()+INTERVAL '30 seconds',updated_at=NOW()
               WHERE id=$1""", recap["id"],
        )
        await conn.execute(
            "UPDATE mw_agent_recap_deliveries SET deadline_at=NOW()+INTERVAL '120 seconds',not_before=NOW()+INTERVAL '120 seconds' WHERE recap_id=$1 AND deadline_at IS NULL",
            recap["id"],
        )
        return
    if recap["state"] not in ("collecting", "waiting") or recap["finalize_after"] > datetime.now(timezone.utc):
        return
    rows = await conn.fetch("SELECT snapshot,asset FROM mw_agent_recap_events WHERE recap_id=$1 ORDER BY occurred_at,id", recap["id"])
    events = [{"snapshot": decode_jsonb(row["snapshot"], {}), "asset": decode_jsonb(row["asset"], None)} for row in rows]
    groups = await conn.fetch(
        """SELECT a.tool,a.kind,a.status,a.result->>'mode' AS mode,a.result->>'queued' AS queued,
           a.result->>'sent' AS sent,COUNT(*) AS count,MIN(a.created_at) AS created_at
           FROM mw_project_agent_steps a JOIN mw_agent_recap_sources s ON s.run_id=a.run_id
           WHERE s.recap_id=$1 GROUP BY a.tool,a.kind,a.status,a.result->>'mode',a.result->>'queued',a.result->>'sent'""", recap["id"],
    )
    totals = {}
    for group in groups:
        payload = {"mode": group["mode"], "queued": group["queued"] == "true"}
        if group.get("sent") == "false":
            payload["sent"] = False
        snapshot = adapters.step_event({**dict(group), "result": payload})
        if snapshot and snapshot.outcome in storyboard.CONSEQUENTIAL:
            key = (snapshot.title, snapshot.outcome)
            previous, count = totals.get(key, (snapshot, 0))
            totals[key] = (previous, count + group["count"])
    aggregates = []
    for (title, outcome), (snapshot, total) in totals.items():
        recorded = sum(1 for entry in events if entry["snapshot"]["kind"] == "action_resolved"
                       and (entry["snapshot"]["title"], entry["snapshot"]["outcome"]) == (title, outcome))
        missing = total - recorded
        if missing > 0:
            snapshot = snapshot.model_copy(update={"facts": [*snapshot.facts, Fact(label="Additional actions with this outcome", value=str(missing))][:6]})
            aggregates.append({"snapshot": snapshot.model_dump(mode="json"), "asset": None})
    if aggregates:
        events += aggregates
        events.sort(key=lambda entry: entry["snapshot"]["occurred_at"])
    useful = any(e["snapshot"]["kind"] in ("action_resolved", "phase_completed") for e in events)
    if not useful or not settings.available(recap["owner_user_id"]):
        await conn.execute("UPDATE mw_agent_recaps SET state='skipped',last_error_code=$2 WHERE id=$1", recap["id"], "no_useful_evidence" if not useful else "disabled")
        await scrub_steps(conn, recap["id"])
        return
    # The request card contains only a bounded root title; never the raw chat.
    request = Event(kind="request", title=recap["title"], occurred_at=recap["created_at"],
                    facts=[Fact(label="Elapsed minutes", value=str(max(0, round((recap["source_completed_at"] - recap["created_at"]).total_seconds() / 60))))])
    events.insert(0, {"snapshot": request.model_dump(mode="json"), "asset": None})
    manifest = storyboard.build(events)
    await conn.execute(
        """UPDATE mw_agent_recaps SET state='queued',manifest=$2::jsonb,manifest_sha256=$3,
           outcome=$4,next_attempt_at=NOW(),updated_at=NOW() WHERE id=$1""",
        recap["id"], manifest.model_dump_json(), manifest.digest(),
        "partial" if any(s.event.outcome in storyboard.CONSEQUENTIAL for s in manifest.scenes) else "observed",
    )
    # The manifest holds its own copy now.
    await scrub_steps(conn, recap["id"])


async def _collect_failed(conn, recap_id, exc):
    """Rolled back, a candidate still moves: to the back of the queue when
    the failure may pass, else (or after a week) to `failed`, so one bad
    recap never starves the rest of collection."""
    final = not isinstance(exc, TRANSIENT)
    try:
        await conn.execute(
            """UPDATE mw_agent_recaps SET updated_at=NOW(),
                   source_completed_at=CASE WHEN $2 AND state='skipped' THEN COALESCE(source_completed_at,NOW())
                       ELSE source_completed_at END,
                   last_error_code=CASE WHEN ($2 OR created_at<NOW()-INTERVAL '7 days') AND state<>'skipped'
                       THEN 'collect_failed' ELSE last_error_code END,
                   state=CASE WHEN ($2 OR created_at<NOW()-INTERVAL '7 days') AND state<>'skipped'
                       THEN 'failed' ELSE state END
               WHERE id=$1 AND state IN ('collecting','waiting','skipped')""", recap_id, final,
        )
    except Exception:
        logger.warning("recap collection failure not recorded recap=%s", recap_id, exc_info=True)


async def sweep() -> bool:
    """Return whether this dispatcher owns the next self-rescheduled sweep."""
    async with connection_or_direct() as conn:
        if not await conn.fetchval("SELECT to_regclass('mw_agent_recaps')"):
            return False
        if not settings.enabled() and not await conn.fetchval(OUTSTANDING):
            return False
        # Inserted enabled, like schedule_auto_generation's: completion email
        # handed to a recap depends on this sweep. Disabling it hands new
        # completions back to their own senders (`delivery.own_mail`).
        await conn.execute(
            """INSERT INTO scheduler_settings(task_key,display_name,enabled,max_per_cycle)
               VALUES('espresso_recaps','Espresso recap recovery',TRUE,50) ON CONFLICT DO NOTHING""",
        )
        claimed = await conn.fetchval(
            """UPDATE scheduler_settings SET last_run_at=NOW() WHERE task_key='espresso_recaps' AND enabled
               AND (last_run_at IS NULL OR last_run_at<NOW()-INTERVAL '45 seconds') RETURNING true""",
        )
        if not claimed:
            return False
        await conn.execute(
            """UPDATE mw_agent_recap_deliveries SET state='unknown',last_error_code='send_lease_expired'
               WHERE state='sending' AND lease_until<NOW()""",
        )
        await conn.execute(
            """UPDATE mw_agent_recaps SET state=CASE WHEN render_attempts<3 AND manual_retry_request_id IS NULL THEN 'queued' ELSE 'failed' END,
               render_token=NULL,lease_until=NULL,next_attempt_at=NOW()+INTERVAL '30 seconds',last_error_code='render_lease_expired'
               WHERE state='rendering' AND lease_until<NOW()""",
        )
        await conn.execute(
            """UPDATE mw_agent_recaps SET state='failed',last_error_code='render_queue_timeout'
               WHERE state='queued' AND updated_at<NOW()-INTERVAL '1 hour'""",
        )
        candidates = await conn.fetch(
            """SELECT id FROM mw_agent_recaps r WHERE state IN ('collecting','waiting')
               OR (state='skipped' AND source_completed_at IS NULL)
               ORDER BY updated_at,id LIMIT 50""",
        )
        for candidate in candidates:
            try:
                async with conn.transaction():
                    recap = await conn.fetchrow("SELECT * FROM mw_agent_recaps WHERE id=$1 FOR UPDATE SKIP LOCKED", candidate["id"])
                    if recap:
                        await collect(conn, recap)
                        await conn.execute("UPDATE mw_agent_recaps SET updated_at=NOW() WHERE id=$1", recap["id"])
            except Exception as exc:
                logger.warning("recap reconciliation failed recap=%s", candidate["id"], exc_info=True)
                await _collect_failed(conn, candidate["id"], exc)
        # Removing a source/account can cascade bindings outside our services.
        invalid = await conn.fetch(f"SELECT r.id FROM mw_agent_recaps r WHERE state NOT IN ('deleted','expired') AND NOT ({VALID}) LIMIT 50")
        expired = await conn.fetch("SELECT id FROM mw_agent_recaps WHERE state='ready' AND expires_at<=NOW() LIMIT 50")
        for row in [*invalid, *expired]:
            async with conn.transaction():
                await tombstone(conn, row["id"], state="expired" if row in expired else "deleted")
        await conn.execute(
            """UPDATE mw_agent_recap_deliveries d SET not_before=NOW() FROM mw_agent_recaps r
               WHERE d.recap_id=r.id AND d.state='pending' AND d.deadline_at IS NOT NULL
               AND r.state IN ('ready','failed','skipped') AND d.not_before>NOW()""",
        )
        renders = await _lease(conn, "mw_agent_recaps", "state='queued' AND next_attempt_at<=NOW()", "next_attempt_at")
        deliveries = await _lease(conn, "mw_agent_recap_deliveries",
                                  "state IN ('pending','retry_wait') AND deadline_at IS NOT NULL AND not_before<=NOW()", "not_before")
        cleanup = await _lease(conn, "mw_agent_recap_cleanup_jobs", "state='pending' AND not_before<=NOW()", "not_before")
    from app.workers.tasks.recaps import cleanup_recap, deliver_recap, render_recap
    for task, rows, queue in ((render_recap, renders, settings.RENDER_QUEUE), (deliver_recap, deliveries, "celery"), (cleanup_recap, cleanup, settings.RENDER_QUEUE)):
        for row in rows:
            task.apply_async(args=[str(row["id"])], queue=queue, expires=DISPATCH_SECONDS)
    return True


async def _lease(conn, table, due, order):
    """Mark up to 50 due rows dispatched and return them. A row is due again
    only once its job claims it (clearing the mark) or the lease runs out."""
    return await conn.fetch(
        f"""UPDATE {table} SET dispatched_at=NOW() WHERE id IN (
               SELECT id FROM {table} WHERE {due}
               AND (dispatched_at IS NULL OR dispatched_at<NOW()-make_interval(secs=>$1))
               ORDER BY {order} LIMIT 50 FOR UPDATE SKIP LOCKED) RETURNING id""", float(DISPATCH_SECONDS),
    )


async def render_job(recap_id):
    token = uuid4()
    async with connection_or_direct() as conn, conn.transaction():
        row = await conn.fetchrow(
            f"""UPDATE mw_agent_recaps r SET state='rendering',render_token=$2,render_attempts=render_attempts+1,
                lease_until=NOW()+INTERVAL '6 minutes',dispatched_at=NULL,updated_at=NOW()
                WHERE id=$1 AND state='queued' AND next_attempt_at<=NOW()
                AND (render_attempts<3 OR (manual_retry_request_id IS NOT NULL AND render_attempts<4))
                AND {VALID} RETURNING r.*""", recap_id, token,
        )
        if not row:
            return
        pref = await conn.fetchval("SELECT enabled FROM mw_agent_recap_preferences WHERE user_id=$1 AND company_id=$2", row["owner_user_id"], row["company_id"])
        if not pref or not settings.available(row["owner_user_id"]):
            await conn.execute("UPDATE mw_agent_recaps SET state='skipped',render_token=NULL,last_error_code='disabled' WHERE id=$1", recap_id)
            return
        prefix = f"espresso-recaps/{row['company_id']}/{row['owner_user_id']}/{recap_id}/renders/{token}/{uuid4()}/"
        await conn.execute(
            "INSERT INTO mw_agent_recap_cleanup_jobs(bucket,prefix,not_before) VALUES($1,$2,NOW()+INTERVAL '30 days') ON CONFLICT DO NOTHING",
            get_settings().s3_private_bucket, prefix,
        )
    try:
        manifest = Manifest.model_validate(decode_jsonb(row["manifest"], {}))
        if manifest.digest() != row["manifest_sha256"]:
            raise ValueError("manifest_checksum_mismatch")
        from .render import render
        with tempfile.TemporaryDirectory(prefix="espresso-recap-") as scratch:
            result = await asyncio.wait_for(render(manifest, Path(scratch)), timeout=225)
            video = await storage.upload(result.pop("video_path"), prefix + "video.mp4", "video/mp4", limit=settings.OUTPUT_BYTES)
            poster = await storage.upload(result.pop("poster_path"), prefix + "poster.png", "image/png", limit=4 * 1024 * 1024)
            result.update(video=video.model_dump(), poster=poster.model_dump())
        async with connection_or_direct() as conn:
            ready = await conn.fetchval(
                f"""UPDATE mw_agent_recaps r SET state='ready',output_manifest=$3::jsonb,ready_at=NOW(),
                    expires_at=NOW()+INTERVAL '30 days',lease_until=NULL,updated_at=NOW()
                    WHERE id=$1 AND render_token=$2 AND state='rendering' AND {VALID}
                    AND EXISTS (SELECT 1 FROM mw_agent_recap_preferences p WHERE p.user_id=r.owner_user_id
                        AND p.company_id=r.company_id AND p.enabled) RETURNING true""", recap_id, token, json.dumps(result),
            )
            if not ready:
                await conn.execute("UPDATE mw_agent_recap_cleanup_jobs SET not_before=NOW() WHERE prefix=$1", prefix)
    except Exception as exc:
        logger.warning("recap render failed recap=%s type=%s", recap_id, type(exc).__name__)
        transient = not isinstance(exc, ValueError) and row["render_attempts"] < 3 and row["manual_retry_request_id"] is None
        async with connection_or_direct() as conn:
            await conn.execute(
                """UPDATE mw_agent_recaps SET state=$3,render_token=NULL,lease_until=NULL,last_error_code=$4,
                   next_attempt_at=NOW()+make_interval(secs=>$5),updated_at=NOW()
                   WHERE id=$1 AND render_token=$2 AND state='rendering'""",
                recap_id, token, "queued" if transient else "failed", type(exc).__name__, 30.0 if row["render_attempts"] == 1 else 120.0,
            )
            await conn.execute("UPDATE mw_agent_recap_cleanup_jobs SET not_before=NOW()+INTERVAL '10 minutes' WHERE prefix=$1", prefix)


async def cleanup_job(cleanup_id):
    async with connection_or_direct() as conn:
        row = await conn.fetchrow("SELECT * FROM mw_agent_recap_cleanup_jobs WHERE id=$1 AND state='pending' AND not_before<=NOW()", cleanup_id)
    if not row:
        return
    done = await storage.cleanup(row["bucket"], row["prefix"])
    async with connection_or_direct() as conn:
        await conn.execute("UPDATE mw_agent_recap_cleanup_jobs SET state=$2,attempts=attempts+1,not_before=NOW()+INTERVAL '1 minute',dispatched_at=NULL WHERE id=$1", cleanup_id, "done" if done else "pending")
