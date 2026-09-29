"""Agent-card runs: read a card's result rounds, or run the agent again.

Runs start on their own when an agent card is created or sent back from review
(see `tasks.py`); these endpoints are the read side and the manual retry.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_company_member
from app.matcha.routes.matcha_work._shared import (
    _can_edit_project,
    _verify_project_access,
)

router = APIRouter()


def _jsonb(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _iso(value):
    return value.isoformat() if value is not None else None


async def _load_task(conn, project_id: UUID, task_id: UUID):
    task = await conn.fetchrow(
        """SELECT id, project_id, company_id, title, description, category, board_column
           FROM mw_tasks WHERE id = $1 AND project_id = $2""",
        task_id, project_id,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(task)


@router.get("/projects/{project_id}/tasks/{task_id}/agent-runs")
async def list_agent_runs_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Every agent pass on this card, newest first, with its steps, plus the
    caller's purchase handoffs for it."""
    await _verify_project_access(project_id, current_user)
    async with get_connection() as conn:
        await _load_task(conn, project_id, task_id)
        runs = await conn.fetch(
            """SELECT id, round, status, result, error, search_calls, model_calls,
                      created_at, started_at, completed_at
               FROM mw_project_agent_runs
               WHERE task_id = $1 AND project_id = $2 AND kind = 'card_agent'
               ORDER BY created_at DESC
               LIMIT 30""",
            task_id, project_id,
        )
        steps = await conn.fetch(
            """SELECT run_id, seq, kind, label, status
               FROM mw_project_agent_steps
               WHERE run_id = ANY($1::uuid[])
               ORDER BY run_id, seq""",
            [r["id"] for r in runs],
        ) if runs else []
        # Only your own purchase handoffs: they carry your card's last 4.
        purchases = await conn.fetch(
            """SELECT id, run_id, item_name, retailer, checkout_url, amount, currency,
                      card_last4, status, created_at
               FROM mw_agent_purchase_requests
               WHERE task_id = $1 AND user_id = $2
               ORDER BY created_at DESC
               LIMIT 20""",
            task_id, current_user.id,
        )
    by_run: dict[UUID, list[dict]] = {}
    for step in steps:
        by_run.setdefault(step["run_id"], []).append({
            "seq": step["seq"], "kind": step["kind"], "label": step["label"], "status": step["status"],
        })
    return {
        "runs": [
            {
                "id": str(r["id"]),
                "round": r["round"],
                "status": r["status"],
                "result": _jsonb(r["result"]),
                "error": r["error"],
                "search_calls": r["search_calls"],
                "model_calls": r["model_calls"],
                "created_at": _iso(r["created_at"]),
                "started_at": _iso(r["started_at"]),
                "completed_at": _iso(r["completed_at"]),
                "steps": by_run.get(r["id"], []),
            }
            for r in runs
        ],
        "purchases": [
            {
                "id": str(p["id"]),
                "run_id": str(p["run_id"]) if p["run_id"] else None,
                "item_name": p["item_name"],
                "retailer": p["retailer"],
                "checkout_url": p["checkout_url"],
                "amount": float(p["amount"]) if p["amount"] is not None else None,
                "currency": p["currency"],
                "card_last4": p["card_last4"],
                "status": p["status"],
                "created_at": _iso(p["created_at"]),
            }
            for p in purchases
        ],
    }


@router.post(
    "/projects/{project_id}/tasks/{task_id}/agent-runs",
    status_code=status.HTTP_202_ACCEPTED,
)
async def rerun_agent_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Run the agent again on this card (after a failure, or a manual move
    back to To do)."""
    from app.matcha.services.matcha_work.agent_card.enqueue import enqueue_card_agent

    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You have read-only access to this project.")
    async with get_connection() as conn:
        task = await _load_task(conn, project_id, task_id)
    return await enqueue_card_agent(task=task, user=current_user, reason="rerun")
