"""Celery entry point for the collab-chat Huume draft-PR agent."""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from ..celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.huume_code.run_huume_code")
def run_huume_code(run_id: str) -> None:
    asyncio.run(_run(UUID(run_id)))


@celery_app.task(name="app.workers.tasks.huume_code.reconcile_stale_runs")
def reconcile_stale_runs() -> None:
    asyncio.run(_reconcile())


async def _reconcile() -> None:
    from app.database import connection_or_direct
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE huume_code_runs SET status='failed', completed_at=NOW(),
                   error=COALESCE(error, 'Interrupted before completion; ask Huume again.')
               WHERE status='running' AND started_at < NOW() - INTERVAL '15 minutes'"""
        )


async def _run(run_id: UUID) -> None:
    from app.database import connection_or_direct
    from app.matcha.services.huume_code import agent, chat, store

    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """UPDATE huume_code_runs SET status='running', started_at=NOW()
               WHERE id=$1 AND status='queued'
               RETURNING company_id, project_id, channel_id, trigger_message_id""", run_id,
        )
        if not row:
            return
        project = await conn.fetchrow("SELECT github_repo, github_branch FROM mw_projects WHERE id=$1", row["project_id"])
        request = await conn.fetchval("SELECT content FROM channel_messages WHERE id=$1", row["trigger_message_id"])
    if not project or not project["github_repo"]:
        await store.mark_run(run_id, status="failed", error="No GitHub repo is connected.")
        await chat.post_as_huume(row["company_id"], row["channel_id"], "I couldn't start: connect a GitHub repo in Elements first.")
        return
    try:
        await agent.run_huume_code(
            run_id=run_id, company_id=row["company_id"], project_id=row["project_id"], channel_id=row["channel_id"],
            request=request or "", repo=project["github_repo"], base_branch=project["github_branch"] or "main",
        )
    except Exception as exc:
        logger.exception("Huume code run failed run=%s", run_id)
        await store.mark_run(run_id, status="failed", error=str(exc)[:2000])
        await chat.post_as_huume(row["company_id"], row["channel_id"], f"I couldn't complete that run: {str(exc)[:500]}")
