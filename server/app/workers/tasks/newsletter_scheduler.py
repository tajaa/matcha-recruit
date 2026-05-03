"""Celery task: dispatch newsletters whose scheduled_at has elapsed.

Pattern mirrors discipline_expiry — runs once per worker startup; systemd
restarts the worker every ~15 minutes so this effectively becomes a
15-minute beat. The dispatcher gates on `scheduler_settings.task_key =
'newsletter_scheduler'` being enabled, then atomically claims each due
newsletter (status: scheduled → sending) before dispatching the send.

Idempotent — only operates on rows where
  status = 'scheduled' AND scheduled_at <= NOW() AND is_deleted = FALSE
and the claim is a single UPDATE so two beats can't double-send.
"""

import asyncio
from uuid import UUID

from ..celery_app import celery_app
from ..utils import get_db_connection


async def _dispatch_newsletter_scheduler() -> dict:
    conn = await get_db_connection()
    try:
        try:
            sched_row = await conn.fetchrow(
                "SELECT enabled FROM scheduler_settings WHERE task_key = 'newsletter_scheduler'"
            )
        except Exception:
            sched_row = None

        if sched_row and not sched_row["enabled"]:
            print("[Newsletter Scheduler] Scheduler disabled, skipping.")
            return {"sent": 0, "skipped": True}
    finally:
        await conn.close()

    from app.core.services import newsletter_service
    due = await newsletter_service.list_due_scheduled_newsletters(limit=25)
    if not due:
        return {"sent": 0}

    sent = 0
    for row in due:
        newsletter_id: UUID = row["id"]
        try:
            # send_newsletter performs its own atomic UPDATE that flips
            # status from 'scheduled' (or stale 'sending') to 'sending' in
            # one statement, which is also the race-safe claim — two beats
            # firing concurrently can't both claim the same row. We don't
            # pre-claim here because that would set status='sending' and
            # then send_newsletter's WHERE clause would reject the same row.
            await newsletter_service.send_newsletter(newsletter_id, actor_id=None)
            sent += 1
        except ValueError:
            # send_newsletter raises if the row was already claimed by
            # another beat or the user manually un-scheduled it. Both are
            # benign — skip silently.
            continue
        except Exception as exc:
            print(f"[Newsletter Scheduler] Send failed for {newsletter_id}: {exc}")
            # Roll back to scheduled so the next beat retries, but bump the
            # scheduled_at by 5 minutes so we don't hot-loop on a broken
            # newsletter every cycle.
            try:
                conn = await get_db_connection()
                try:
                    await conn.execute(
                        """UPDATE newsletters
                              SET status = 'scheduled',
                                  scheduled_at = NOW() + INTERVAL '5 minutes',
                                  scheduled_send_started_at = NULL
                            WHERE id = $1 AND status = 'sending'""",
                        newsletter_id,
                    )
                finally:
                    await conn.close()
            except Exception:
                pass
    print(f"[Newsletter Scheduler] Dispatched {sent} of {len(due)} due newsletter(s).")
    return {"sent": sent, "due": len(due)}


@celery_app.task(name="newsletter.scheduler", bind=True, max_retries=1)
def run_newsletter_scheduler(self):
    """Dispatch any newsletters whose scheduled_at has elapsed."""
    try:
        return asyncio.run(_dispatch_newsletter_scheduler())
    except Exception as e:
        print(f"[Newsletter Scheduler] Task failed: {e}")
        raise self.retry(exc=e, countdown=120)
