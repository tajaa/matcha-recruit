"""Celery entry points for durable Espresso project-agent tasks."""
from __future__ import annotations

import logging
from uuid import UUID

from ..celery_app import celery_app
from ..utils import run_with_chat_fanout

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.project_agent.run_repo_question")
def run_repo_question(run_id: str) -> None:
    run_with_chat_fanout(_run(UUID(run_id)))


@celery_app.task(name="app.workers.tasks.project_agent.run_task_draft")
def run_task_draft(run_id: str) -> None:
    run_with_chat_fanout(_run(UUID(run_id)))


@celery_app.task(name="app.workers.tasks.project_agent.reconcile_stale_runs")
def reconcile_stale_runs() -> None:
    run_with_chat_fanout(_reconcile())


async def _reconcile() -> None:
    from app.database import connection_or_direct

    async with connection_or_direct() as conn:
        stale = await conn.fetch(
            """UPDATE mw_project_agent_runs
               SET status='failed', completed_at=NOW(),
                   error=COALESCE(error, 'Interrupted before completion; start the task again.')
               WHERE status IN ('queued', 'running')
                 AND COALESCE(started_at, created_at) < NOW() - INTERVAL '15 minutes'
               RETURNING kind, project_id, task_id, id, channel_id, company_id"""
        )
    # An agent card whose run died (worker restart mid-run) would otherwise sit
    # in In progress forever with a stale status line; say what happened.
    from app.matcha.services.matcha_work.agent_card import board
    from app.workers.tasks.agent_card import FAILED_NOTE

    for row in stale:
        if row["kind"] == "assistant" and row["channel_id"] is not None:
            # The progress card in the chat would otherwise spin forever.
            from app.matcha.services.matcha_work.agent_runtime import assistant

            await assistant.report_failure(dict(row), "It was interrupted. Ask me again.")
            continue
        if row["kind"] != "card_agent" or row["task_id"] is None:
            continue
        task = await board.set_progress(
            row["task_id"], FAILED_NOTE.format(reason="the run was interrupted."), force=True,
        )
        if task:
            await board.publish_task_updated(row["project_id"], task)


async def _run(run_id: UUID) -> None:
    from app.database import connection_or_direct
    from app.matcha.services.matcha_work.project_agent import agent, chat, store
    from app.matcha.services.matcha_work.project_agent import task_draft_agent

    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """UPDATE mw_project_agent_runs
               SET status='running', started_at=NOW()
               WHERE id=$1 AND status='queued'
               RETURNING company_id, project_id, channel_id, requested_by, prompt,
                         kind""",
            run_id,
        )
        if not row:
            return
        project = await conn.fetchrow(
            """SELECT p.title, p.github_repo, p.github_branch,
                      (SELECT role FROM users WHERE id=$3) AS requester_role
               FROM mw_projects p WHERE p.id=$1 AND p.company_id=$2""",
            row["project_id"],
            row["company_id"],
            row["requested_by"],
        )

    if not project or not project["github_repo"]:
        message = "I couldn't start because this project no longer has a connected GitHub repository."
        await store.mark_run(run_id, status="failed", error=message)
        if row["kind"] == "repo_question" and row["channel_id"]:
            await chat.post_as_espresso(row["company_id"], row["channel_id"], message)
        return

    try:
        if row["kind"] == "repo_question":
            if not row["channel_id"]:
                raise RuntimeError("Repository-question run is missing its channel.")
            result = await agent.run_repo_question(
                run_id=run_id,
                company_id=row["company_id"],
                project_id=row["project_id"],
                channel_id=row["channel_id"],
                question=row["prompt"],
                project_title=project["title"] or "Untitled project",
                repo=project["github_repo"],
                base_branch=project["github_branch"] or "main",
            )
        elif row["kind"] == "task_draft":
            context = await store.load_task_draft_context(row["project_id"])
            result = await task_draft_agent.run_task_draft(
                run_id=run_id,
                company_id=row["company_id"],
                project_id=row["project_id"],
                requested_by=row["requested_by"],
                request=row["prompt"],
                project_title=project["title"] or "Untitled project",
                repo=project["github_repo"],
                base_branch=project["github_branch"] or "main",
                collaborators=context["collaborators"],
                elements=context["elements"],
                recent_done=context["recent_done"],
            )
        else:
            raise RuntimeError(f"Unsupported project-agent task kind: {row['kind']}")

        if project["requester_role"] != "admin":
            try:
                from app.matcha.services.billing import token_budget_service

                total_tokens = int((result.get("token_usage") or {}).get("total_tokens") or 0)
                if total_tokens > 0:
                    async with connection_or_direct() as conn:
                        async with conn.transaction():
                            await token_budget_service.deduct_tokens(
                                conn, row["company_id"], total_tokens,
                            )
            except Exception:
                # The model call already happened and the answer is durable;
                # accounting failure must not replace it with a false user-facing
                # run failure. The AI usage ledger still records the provider call.
                logger.warning(
                    "Failed to deduct project-agent tokens run=%s", run_id,
                    exc_info=True,
                )
    except Exception as exc:
        logger.exception("Espresso project-agent run failed run=%s", run_id)
        detail = str(exc)[:1000]
        await store.mark_run(run_id, status="failed", error=detail)
        if row["kind"] == "repo_question" and row["channel_id"]:
            await chat.post_as_espresso(
                row["company_id"],
                row["channel_id"],
                f"I couldn't answer that from the repository: {detail[:500]}",
            )
