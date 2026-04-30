"""Celery task: auto-archive threads and projects idle for 7+ days without a star/pin.

Threads: is_pinned = true → skip. Otherwise archive if updated_at < NOW() - 7 days.
Projects: any row in mw_project_pins for this project → skip. Otherwise archive if updated_at < NOW() - 7 days.
Only processes status='active' rows. Idempotent.
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection


async def _run_auto_archive() -> dict:
    conn = await get_db_connection()
    try:
        try:
            sched_row = await conn.fetchrow(
                "SELECT enabled FROM scheduler_settings WHERE task_key = 'auto_archive'"
            )
        except Exception:
            sched_row = None

        if sched_row and not sched_row["enabled"]:
            print("[AutoArchive] Scheduler disabled, skipping.")
            return {"threads": 0, "projects": 0, "skipped": True}

        thread_result = await conn.execute(
            """
            UPDATE mw_threads
            SET status = 'archived', updated_at = NOW()
            WHERE status = 'active'
              AND is_pinned = false
              AND updated_at < NOW() - INTERVAL '7 days'
            """,
        )

        project_result = await conn.execute(
            """
            UPDATE mw_projects
            SET status = 'archived', updated_at = NOW()
            WHERE status = 'active'
              AND updated_at < NOW() - INTERVAL '7 days'
              AND NOT EXISTS (
                  SELECT 1 FROM mw_project_pins WHERE project_id = mw_projects.id
              )
            """,
        )

        def _parse_count(tag: str) -> int:
            try:
                return int(tag.split()[-1])
            except Exception:
                return 0

        threads_archived = _parse_count(thread_result)
        projects_archived = _parse_count(project_result)
        print(f"[AutoArchive] Archived {threads_archived} thread(s), {projects_archived} project(s).")
        return {"threads": threads_archived, "projects": projects_archived}
    finally:
        await conn.close()


@celery_app.task(name="matcha_work.auto_archive", bind=True, max_retries=1)
def run_auto_archive(self):
    """Archive threads/projects idle for 7+ days with no star/pin."""
    try:
        result = asyncio.run(_run_auto_archive())
        return result
    except Exception as e:
        print(f"[AutoArchive] Task failed: {e}")
        raise self.retry(exc=e, countdown=120)
