"""Huume's plan approve/execute REST surface — the UI-button counterpart to
approving/executing an onboarding plan from chat (agent.py's
`execute_approved_steps` tool). Both paths funnel through the same pure
verdict (`actions.evaluate_plan_step`) and executor (`actions.execute_plan_steps`).

Mounted at `/matcha-work` (this package's prefix) alongside every other
matcha_work route — `require_feature("huume")` on top of the package's own
`require_feature("matcha_work")` gate, matching the offer/action dispatch's
own re-assertion of the same flag.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.models.auth import CurrentUser
from app.matcha.dependencies import require_admin_or_client, require_feature
from app.matcha.services.matcha_work import matcha_work_document as doc_svc
from app.matcha.services.huume import actions as huume_actions, store as huume_store

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_feature("huume"))])


class ApprovePlanRequest(BaseModel):
    step_keys: Optional[list[str]] = Field(
        default=None,
        description="Plan step keys to approve. Omit or empty for every step still 'proposed'.",
    )


async def _get_owned_thread(thread_id: UUID, current_user: CurrentUser) -> dict:
    from app.matcha.dependencies import get_client_company_id

    company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.post("/threads/{thread_id}/huume/plan/approve")
async def approve_huume_plan(
    thread_id: UUID,
    payload: ApprovePlanRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Flip named (or all proposed) plan steps to `approved`. Does not
    execute anything — see /plan/execute."""
    await _get_owned_thread(thread_id, current_user)

    def mutator(current_plan):
        if not isinstance(current_plan, dict) or not current_plan.get("steps"):
            raise HTTPException(status_code=400, detail="No onboarding plan is staged on this thread yet.")
        return huume_actions.mark_steps_approved(current_plan, payload.step_keys)

    try:
        plan = await huume_store.update_huume_plan(thread_id, mutator)
    except ValueError:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"plan": plan}


@router.post("/threads/{thread_id}/huume/plan/execute")
async def execute_huume_plan(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Run every `approved` step in the staged plan. Steps missing a
    required feature/integration are skipped and reported, not executed —
    that isn't an error. Idempotent: a step with a `record_id` already set
    is refused as "already done" rather than re-run."""
    thread = await _get_owned_thread(thread_id, current_user)
    company_id = thread["company_id"]

    current_plan = (thread.get("current_state") or {}).get("huume_plan")
    if not isinstance(current_plan, dict) or not current_plan.get("steps"):
        raise HTTPException(status_code=400, detail="No onboarding plan is staged on this thread yet.")

    features, integrations = await huume_store.get_thread_features_and_integrations(company_id)
    exec_result = await huume_actions.execute_plan_steps(
        company_id=company_id, actor_user_id=current_user.id, plan=current_plan,
        features=features, integrations=integrations,
    )
    executed_by_key = {s["key"]: s for s in exec_result.plan.get("steps", [])}

    def mutator(latest_plan):
        # Merge the just-executed step results onto whatever the plan looks
        # like right now (a concurrent approve click may have landed between
        # our unlocked read above and this locked write) — overlay only the
        # steps THIS call actually touched, by key, rather than overwriting
        # the whole plan wholesale.
        base = latest_plan if isinstance(latest_plan, dict) and latest_plan.get("steps") else current_plan
        merged_steps = []
        for step in base.get("steps", []):
            touched = executed_by_key.get(step.get("key"))
            merged_steps.append(touched if touched else step)
        merged = {**base, "steps": merged_steps, "employee_id": exec_result.plan.get("employee_id") or base.get("employee_id")}
        if all(s.get("status") in ("done", "skipped", "failed") for s in merged_steps):
            merged["status"] = "done"
        return merged

    try:
        saved_plan = await huume_store.update_huume_plan(thread_id, mutator)
    except ValueError:
        raise HTTPException(status_code=404, detail="Thread not found")

    summary = "; ".join(exec_result.summaries) if exec_result.summaries else "No approved steps were ready to run."
    try:
        await doc_svc.add_message(
            thread_id, "assistant", f"Ran the approved onboarding steps: {summary}",
            metadata={"huume_event": "plan_executed"},
        )
    except Exception:
        logger.warning("huume: failed to post plan-execution summary message for thread %s", thread_id, exc_info=True)

    return {"plan": saved_plan, "summary": summary}
