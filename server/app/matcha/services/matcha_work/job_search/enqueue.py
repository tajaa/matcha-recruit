"""Gate, create and dispatch one job search.

`preflight` is every refusal knowable up front: a personal workspace, a search
provider, the plan, the `jobs` consent, the token budget and a rate limit.
`create_search` then re-checks the monthly cap atomically, under a per-person
advisory lock, inserts the search and dispatches its first phase.
"""
from __future__ import annotations

import json
import logging
import os
from uuid import UUID, uuid4

import asyncpg
from fastapi import HTTPException

from app.database import connection_or_direct
from app.matcha.models.matcha_work.job_search import JobSearchCreate
from app.matcha.services.billing.entitlements_service import PLAN_PRO, require_plan

from . import providers, ranking
from .quota import job_search_usage, limit_for_plan, usage_payload, used_this_month
from .service import end_stale, find_by_request, search_view

logger = logging.getLogger(__name__)

ABILITY_KEY = "jobs"
ENTITLEMENT = "job_search"
# Unset: Celery's default queue. A search is a chain of short tasks, so on the
# single-slot main worker it interleaves with everything else; set this (or
# AGENT_CARD_QUEUE) to move it onto the agent worker.
_QUEUE_ENVS = ("AGENT_JOBS_QUEUE", "AGENT_CARD_QUEUE")
def queue_for() -> str | None:
    for name in _QUEUE_ENVS:
        if os.getenv(name):
            return os.getenv(name)
    return None


def _is_admin(user) -> bool:
    return (getattr(user, "role", "") or "").lower() == "admin"


def _limit_error(usage: dict) -> HTTPException:
    return HTTPException(status_code=429, detail={
        "code": "job_search_limit",
        "message": "You've used this month's job searches.",
        **usage,
    })


async def consent_granted(user_id: UUID) -> bool:
    from app.matcha.services.matcha_work.agent_runtime import grants

    rows = await grants.list_rows(user_id)
    return grants.is_active(rows.get(ABILITY_KEY), ABILITY_KEY)


async def preflight(user, company_id: UUID, *, consent_version: str | None = None) -> str | None:
    """Raises HTTPException. Returns the plan (None for an admin)."""
    from app.matcha.services.matcha_work.agent_runtime.enqueue import workspace_enabled

    if not await workspace_enabled(company_id):
        raise HTTPException(status_code=403, detail={
            "code": "feature_disabled",
            "message": "Job search comes with a personal Espresso account.",
        })
    if not providers.configured():
        raise HTTPException(status_code=503, detail="Job search isn't available right now.")
    plan = None
    if not _is_admin(user):
        plan = await require_plan(user.id, PLAN_PRO, ENTITLEMENT)
        usage = await job_search_usage(user.id, plan=plan)
        if usage["remaining"] <= 0:
            raise _limit_error(usage)
    if not await consent_granted(user.id):
        from app.matcha.services.matcha_work.agent_runtime import grants

        # Raises 409 consent_required (with the disclosure) unless they just agreed.
        await grants.enable(user.id, company_id, ABILITY_KEY, consent_version=consent_version)
    if not _is_admin(user):
        from app.matcha.services.billing import token_budget_service
        from app.core.services.redis_cache import check_rate_limit

        await token_budget_service.check_token_budget(company_id)
        await check_rate_limit(str(user.id), "espresso_job_search_user", 6, 86400)
    return plan


async def dispatch(search_id: UUID, token: UUID, *, countdown: int = 0) -> None:
    """Queue the search's next phase. Raises when the broker refuses it."""
    from app.workers.tasks.job_search import run_job_search_phase

    run_job_search_phase.apply_async(
        args=[str(search_id), str(token)], queue=queue_for(), countdown=max(0, int(countdown)),
    )


async def create_search(user, company_id: UUID, body: JobSearchCreate) -> dict:
    # A retried create (the first answer was lost) gets the search it already
    # started, before any cap or rate limit could refuse it.
    existing = await find_by_request(user.id, body.request_id)
    if existing is not None:
        return existing
    plan = await preflight(user, company_id, consent_version=body.consent_version)
    limit = limit_for_plan(plan) if plan is not None else None
    weights = ranking.clean_weights(body.weights.model_dump() if body.weights else None)
    token = uuid4()
    title = body.title or (body.criteria.titles[0] if body.criteria.titles else body.ask[:80])
    from .agent_phase import default_model

    # Settled now, like the assistant's: a later admin change applies to new searches.
    model = await default_model()
    async with connection_or_direct() as conn:
        async with conn.transaction():
            # Count-then-insert is atomic per person: two creates at once can't
            # both slip under the cap.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"{user.id}:job_search_cap",
            )
            existing = await conn.fetchrow(
                "SELECT * FROM mw_job_searches WHERE user_id = $1 AND request_id = $2",
                user.id, body.request_id,
            )
            if existing is not None:  # a retried create
                return search_view(existing)
            # A chain that died long ago would hold the one-live-search index forever.
            await end_stale(conn, user.id)
            if limit is not None:
                used = await used_this_month(conn, user.id)
                if used >= limit:
                    raise _limit_error(usage_payload(limit, used))
            try:
                row = await conn.fetchrow(
                    """INSERT INTO mw_job_searches
                           (request_id, user_id, company_id, title, ask, criteria, weights,
                            weights_source, use_resume, status, dispatch_token, progress, model)
                       VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, 'queued', $10,
                               '{"note": "Queued."}'::jsonb, $11)
                       RETURNING *""",
                    body.request_id, user.id, company_id, title[:120], body.ask,
                    json.dumps(body.criteria.model_dump()), json.dumps(weights),
                    "user" if body.weights else "default", body.use_resume, token, model,
                )
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=409, detail={
                    "code": "job_search_running",
                    "message": "A job search is already running. Cancel it or wait for it to finish.",
                })
    try:
        await dispatch(row["id"], token)
    except Exception:
        # Broker down: a queued row with nothing to run it would hold the
        # live-search index. Failed searches are free.
        logger.exception("job search dispatch failed search=%s", row["id"])
        async with connection_or_direct() as conn:
            await conn.execute(
                """UPDATE mw_job_searches
                   SET status = 'failed', error = 'Could not be queued.', dispatch_token = NULL,
                       completed_at = NOW(), updated_at = NOW()
                   WHERE id = $1 AND status = 'queued'""",
                row["id"],
            )
        raise HTTPException(status_code=503, detail="Couldn't start the search right now. Try again in a moment.")
    logger.info("job search queued search=%s user=%s", row["id"], user.id)
    return search_view(row)


async def redraft_approach(user, search_id: UUID, lead_id: UUID) -> dict:
    """Draft (or redraft) the approach for one job of a finished or cancelled search."""
    from app.core.services.redis_cache import check_rate_limit

    from .service import get_search, requeue_approach

    if not _is_admin(user):
        await check_rate_limit(str(user.id), "espresso_job_search_redraft", 10, 3600)
    _search, token = await requeue_approach(search_id, lead_id, user.id)
    try:
        await dispatch(search_id, token)
    except Exception:
        # The search stays `approaching`; a status poll restarts it.
        logger.exception("job search redraft dispatch failed search=%s", search_id)
    return await get_search(search_id, user.id)
