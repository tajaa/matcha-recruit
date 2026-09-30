"""Gate and queue one assistant run.

`preflight` is every refusal that can be known up front: the workspace flag,
the plan, today's allowance, the token budget, the rate limit. It runs before
anything is written, so a refusal leaves no run row behind.

`enqueue_assistant_run` re-checks what must be atomic: the daily allowance,
under a per-person lock, and one live run per person per conversation, after
sweeping runs whose worker died.
"""
from __future__ import annotations

import logging
import os
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.database import get_connection
from app.matcha.services.billing.entitlements_service import PLAN_PRO, require_plan
from app.matcha.services.huume.routing import LUNA

from .quota import assistant_usage, limit_for_plan, usage_payload, used_today

logger = logging.getLogger(__name__)

ENTITLEMENT = "assistant"
ASSISTANT_MODEL = LUNA
_QUEUE_ENV = "AGENT_ASSISTANT_QUEUE"
_CARD_QUEUE_ENV = "AGENT_CARD_QUEUE"
_BROWSER_QUEUE_ENV = "AGENT_BROWSER_QUEUE"
# Celery's hard task limit is 600s, so a run still live well past that has
# lost its worker. Older than this it stops blocking the next message.
_STALE_RUN_INTERVAL = "11 minutes"
STILL_WORKING = "I'm still working on your last request. Ask me again when that one lands."
INTERRUPTED = "It was interrupted. Ask me again."


def _is_admin(user) -> bool:
    return (getattr(user, "role", "") or "").lower() == "admin"


def _limit_error(usage: dict) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "assistant_run_limit",
            "message": "You've used today's Espresso requests.",
            **usage,
        },
    )


def queue_for(abilities: list[str]) -> str | None:
    """A run that may open a browser goes to the browser worker; nothing else does."""
    if "reservations" in abilities and os.getenv(_BROWSER_QUEUE_ENV):
        return os.getenv(_BROWSER_QUEUE_ENV)
    return os.getenv(_QUEUE_ENV) or os.getenv(_CARD_QUEUE_ENV) or None


async def workspace_enabled(company_id: UUID) -> bool:
    """Whether this workspace gets the assistant: a personal account, never a
    business one (`eligibility.assistant_available`)."""
    from app.core.feature_flags import merge_company_features

    from .eligibility import assistant_available

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT enabled_features, signup_source, COALESCE(is_personal, false) AS is_personal
               FROM companies WHERE id = $1""",
            company_id,
        )
    if not row:
        return False
    features = merge_company_features(row["enabled_features"], row["signup_source"])
    return assistant_available(is_personal=row["is_personal"], features=features)


async def preflight(user, company_id: UUID) -> None:
    """Flag, plan, daily allowance, token budget and rate limit. Raises
    HTTPException. Advisory for the allowance (enqueue re-checks it atomically)."""
    if not await workspace_enabled(company_id):
        raise HTTPException(status_code=403, detail={
            "code": "feature_disabled",
            "message": "The Espresso assistant comes with a personal Espresso account.",
        })
    if _is_admin(user):
        return
    plan = await require_plan(user.id, PLAN_PRO, ENTITLEMENT)
    usage = await assistant_usage(user.id, plan=plan)
    if usage["remaining"] <= 0:
        raise _limit_error(usage)
    from app.matcha.services.billing import token_budget_service

    await token_budget_service.check_token_budget(company_id)

    from app.core.services.redis_cache import check_rate_limit

    await check_rate_limit(str(user.id), "espresso_assistant_user", 30, 3600)


async def enqueue_assistant_run(
    *,
    user,
    company_id: UUID,
    channel_id: UUID,
    trigger_message_id: UUID,
    project_id: UUID | None,
    surface: str,
    prompt: str,
    abilities: list[str],
    resume_prompt_id: UUID | None = None,
    skip_preflight: bool = False,
) -> dict:
    """Insert a queued `assistant` run and dispatch it. Returns `{run_id, status}`."""
    if not skip_preflight:
        await preflight(user, company_id)
    limit: int | None = None
    if not _is_admin(user):
        limit = limit_for_plan(await require_plan(user.id, PLAN_PRO, ENTITLEMENT))

    async with get_connection() as conn:
        async with conn.transaction():
            # Person first, then conversation: every caller takes them in this
            # order, so two enqueues cannot deadlock. The person lock makes
            # count-then-insert atomic.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"{user.id}:assistant_cap",
            )
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"{channel_id}:{user.id}:assistant",
            )
            swept = await conn.fetch(
                f"""UPDATE mw_project_agent_runs
                    SET status = 'failed', completed_at = NOW(),
                        error = COALESCE(error, 'Interrupted before completion.')
                    WHERE channel_id = $1 AND requested_by = $2 AND kind = 'assistant'
                      AND status IN ('queued', 'running')
                      AND COALESCE(started_at, created_at) < NOW() - INTERVAL '{_STALE_RUN_INTERVAL}'
                    RETURNING id, channel_id, company_id""",
                channel_id, user.id,
            )
            if limit is not None:
                used = await used_today(conn, user.id)
                if used >= limit:
                    raise _limit_error(usage_payload(limit, used))
            try:
                run_id = await conn.fetchval(
                    """INSERT INTO mw_project_agent_runs
                       (company_id, project_id, channel_id, requested_by, trigger_message_id,
                        agent_key, kind, prompt, status, model, surface, abilities, resume_prompt_id)
                       VALUES ($1, $2, $3, $4, $5, 'espresso', 'assistant', $6, 'queued', $7, $8, $9, $10)
                       ON CONFLICT (trigger_message_id, agent_key) DO NOTHING
                       RETURNING id""",
                    company_id, project_id, channel_id, user.id, trigger_message_id,
                    prompt[:12_000], ASSISTANT_MODEL, surface, abilities, resume_prompt_id,
                )
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=409, detail=STILL_WORKING)
    if swept:
        # Swept here, the reconciler never sees these rows move, so it is here
        # that the dead run's progress card is closed and the person told.
        from .assistant import report_failure

        for row in swept:
            await report_failure(dict(row), INTERRUPTED)
    if run_id is None:
        # The same message delivered twice: the first delivery owns the run.
        return {"run_id": None, "status": "duplicate"}

    from app.workers.tasks.assistant import run_assistant

    try:
        run_assistant.apply_async(args=[str(run_id)], queue=queue_for(abilities))
    except Exception:
        # Broker down. Don't leave a queued row holding the live-run index
        # (and counting against today) with nothing ever going to run it.
        logger.exception("assistant dispatch failed run=%s", run_id)
        async with get_connection() as conn:
            await conn.execute(
                """UPDATE mw_project_agent_runs
                   SET status = 'failed', completed_at = NOW(), error = 'Could not be queued.'
                   WHERE id = $1 AND status = 'queued'""",
                run_id,
            )
        raise HTTPException(
            status_code=503,
            detail="Couldn't start that right now. Try again in a moment.",
        )
    logger.info("assistant run queued run=%s channel=%s surface=%s", run_id, channel_id, surface)
    return {"run_id": str(run_id), "status": "queued"}
