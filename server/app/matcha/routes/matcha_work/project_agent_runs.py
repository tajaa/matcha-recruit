"""Durable project-agent tasks launched from Espresso project surfaces."""
from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client
from app.matcha.routes.matcha_work._shared import _can_edit_project, _verify_project_access


logger = logging.getLogger(__name__)
router = APIRouter()


def _decode_jsonb(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
    return value


@router.post(
    "/projects/{project_id}/tasks/agent-draft",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_agent_task_draft_endpoint(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Queue a repo-reading Espresso run; the client polls before review."""
    project, role = await _verify_project_access(project_id, current_user)
    # A run reads the repo and spends the workspace token budget, and its output
    # can only land as a task the caller is allowed to create — so read-only
    # collaborators are blocked here, not just at task creation.
    if not _can_edit_project(role):
        raise HTTPException(
            status_code=403,
            detail="You have read-only access to this project.",
        )
    if not project.get("github_repo"):
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "code": "repository_required",
                "message": "Connect a GitHub repository to use agent drafting.",
            },
        )

    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Describe the task you want to create")
    if len(prompt) > 12_000:
        raise HTTPException(status_code=400, detail="Task description is too long (12,000 characters max)")

    raw_key = body.get("request_key")
    try:
        request_key = UUID(str(raw_key)) if raw_key else uuid4()
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="request_key must be a UUID")

    company_id = UUID(str(project["company_id"]))

    from app.core.services.redis_cache import check_rate_limit
    from app.matcha.services.billing import token_budget_service

    if (getattr(current_user, "role", "") or "").lower() != "admin":
        await token_budget_service.check_token_budget(company_id)
    await check_rate_limit(str(current_user.id), "espresso_task_draft_user", 50, 86400)
    await check_rate_limit(str(company_id), "espresso_task_draft_company", 20, 3600)

    # Drafts are pinned to Luna server-side; the run row records the model that
    # actually ran, and a client-sent model is never consulted.
    from app.matcha.services.matcha_work.project_agent.task_draft_agent import TASK_DRAFT_MODEL

    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"{project_id}:{current_user.id}:task_draft",
            )
            # A client may retry the POST after losing the response. Return the
            # original run before applying the one-live-run guard — scoped to
            # the same (project, requester) the advisory lock above serializes
            # on. A bare request_key lookup is global: another tenant reusing a
            # key would be handed this project's run id, and two users sending
            # the same key would race past the lock into the unique index.
            run_id = await conn.fetchval(
                """SELECT id FROM mw_project_agent_runs
                   WHERE request_key=$1 AND agent_key='espresso'
                     AND project_id=$2 AND requested_by=$3""",
                request_key,
                project_id,
                current_user.id,
            )
            if run_id is None:
                live = await conn.fetchval(
                    """SELECT EXISTS(
                           SELECT 1 FROM mw_project_agent_runs
                           WHERE project_id=$1 AND requested_by=$2
                             AND kind='task_draft'
                             AND status IN ('queued','running')
                             AND COALESCE(started_at, created_at) > NOW() - INTERVAL '15 minutes'
                       )""",
                    project_id,
                    current_user.id,
                )
                if live:
                    raise HTTPException(
                        status_code=409,
                        detail="Espresso is already drafting a ticket for you in this project.",
                    )
                run_id = await conn.fetchval(
                    """INSERT INTO mw_project_agent_runs
                       (company_id, project_id, requested_by, agent_key, kind,
                        prompt, status, request_key, model)
                       VALUES ($1,$2,$3,'espresso','task_draft',$4,'queued',$5,$6)
                       RETURNING id""",
                    company_id,
                    project_id,
                    current_user.id,
                    prompt,
                    request_key,
                    TASK_DRAFT_MODEL,
                )

    from app.workers.tasks.project_agent import run_task_draft

    run_task_draft.delay(str(run_id))
    return {"run_id": str(run_id), "status": "queued"}


@router.get("/projects/{project_id}/tasks/agent-draft/{run_id}")
async def get_agent_task_draft_endpoint(
    project_id: UUID,
    run_id: UUID,
    response: Response,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return one caller-owned task-draft run without exposing its audit log.

    The lookup itself is the authorization: it is pinned to this project AND
    this requester, so it can only ever return the caller's own run. Re-running
    full project access here cost ~6 queries on a 2s poll loop.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT id, status, result, error, created_at, started_at, completed_at
               FROM mw_project_agent_runs
               WHERE id=$1 AND project_id=$2 AND requested_by=$3
                 AND agent_key='espresso' AND kind='task_draft'""",
            run_id,
            project_id,
            current_user.id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Task draft run not found")
    response.headers["Cache-Control"] = "no-store"
    return {
        "run_id": str(row["id"]),
        "status": row["status"],
        "draft": _decode_jsonb(row["result"]),
        "error": (row["error"] or "")[:500] or None,
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }
