"""Huume's plan approve/execute REST surface — the UI-button counterpart to
approving/executing an onboarding plan from chat (agent.py's
`execute_approved_steps` tool). Both paths funnel through the same locked
executor (`store.execute_plan_locked`, which wraps `actions.execute_plan_steps`
under a per-(thread, offer) advisory lock — see that function's docstring).

Plans are keyed by offer_id (`current_state.huume_plans`) since a thread can
be onboarding several candidates at once — both routes accept an optional
`offer_id` and fall back to "the sole active plan" when omitted (`actions.
resolve_plan_offer_id`, the same resolver the chat tool path uses), 400ing
with the candidate list when more than one plan is active and no id was given.

Also owns `GET .../huume/record` — the panel-facing counterpart to the chat
tool `show_record`: fetches the normalized record view (`services/huume/
record_view.py`) under the admin's own auth, re-checking that record type's
own feature flag on top of the mount's huume/matcha_work gates. And
`DELETE .../huume/record` — drops one entry from the open-record working
set (`current_state.huume_records`), the `×` on a panel tab.

Mounted at `/matcha-work` (this package's prefix) alongside every other
matcha_work route — `require_feature("huume")` on top of the package's own
`require_feature("matcha_work")` gate, matching the offer/action dispatch's
own re-assertion of the same flag.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.models.auth import CurrentUser
from app.matcha.dependencies import require_admin_or_client, require_feature
from app.matcha.services.matcha_work import matcha_work_document as doc_svc
from app.matcha.services.huume import actions as huume_actions, record_view, store as huume_store

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_feature("huume"))])


class ApprovePlanRequest(BaseModel):
    offer_id: Optional[str] = Field(
        default=None,
        description="Which candidate's plan. Required unless the thread has exactly one active plan.",
    )
    step_keys: Optional[list[str]] = Field(
        default=None,
        description="Plan step keys to approve. Omit or empty for every step still 'proposed'.",
    )


class ExecutePlanRequest(BaseModel):
    offer_id: Optional[str] = Field(
        default=None,
        description="Which candidate's plan. Required unless the thread has exactly one active plan.",
    )


async def _get_owned_thread(thread_id: UUID, current_user: CurrentUser) -> tuple[dict, UUID]:
    """Returns (thread, caller_company_id) — the caller's own company_id is
    already resolved here, so callers that need to compare it against the
    thread's company_id (cross-tenant collaborator check) don't re-fetch it."""
    from app.matcha.dependencies import get_client_company_id

    caller_company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, caller_company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread, caller_company_id


def _resolve_offer_id(current_state: dict, requested: Optional[str]) -> str:
    """Plans are keyed by offer_id (a thread may be onboarding several
    candidates at once) — resolve which one this call means, the same rule
    the chat tool path uses via `actions.resolve_plan_offer_id`."""
    plans = (current_state or {}).get("huume_plans") or {}
    offer_id, err = huume_actions.resolve_plan_offer_id(plans, requested, built_this_turn=set())
    if err:
        raise HTTPException(status_code=400, detail=err)
    return offer_id


@router.post("/threads/{thread_id}/huume/plan/approve")
async def approve_huume_plan(
    thread_id: UUID,
    payload: ApprovePlanRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Flip named (or all proposed) plan steps to `approved`. Does not
    execute anything — see /plan/execute."""
    thread, _ = await _get_owned_thread(thread_id, current_user)
    offer_id = _resolve_offer_id(thread.get("current_state") or {}, payload.offer_id)

    def mutator(current_plan):
        if not isinstance(current_plan, dict) or not current_plan.get("steps"):
            raise HTTPException(status_code=400, detail="No onboarding plan is staged for that offer.")
        return huume_actions.mark_steps_approved(current_plan, payload.step_keys)

    try:
        plan = await huume_store.update_huume_plan(thread_id, offer_id, mutator)
    except ValueError:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"plan": plan, "offer_id": offer_id}


@router.post("/threads/{thread_id}/huume/plan/execute")
async def execute_huume_plan(
    thread_id: UUID,
    payload: ExecutePlanRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Run every `approved` step in the staged plan. Steps missing a
    required feature/integration are skipped and reported, not executed —
    that isn't an error. Idempotent: a step with a `record_id` already set
    is refused as "already done" rather than re-run.

    Delegates to `store.execute_plan_locked` — the SAME path the chat tool's
    execute_approved_steps handler uses, under a per-(thread, offer)
    advisory lock, so a chat-driven execute and a UI-button execute for the
    same candidate can never race and clobber each other's results."""
    thread, _ = await _get_owned_thread(thread_id, current_user)
    company_id = thread["company_id"]
    offer_id = _resolve_offer_id(thread.get("current_state") or {}, payload.offer_id)

    features, integrations = await huume_store.get_thread_features_and_integrations(company_id)
    try:
        exec_result = await huume_store.execute_plan_locked(
            thread_id=thread_id, company_id=company_id, actor_user_id=current_user.id, offer_id=offer_id,
            features=features, integrations=integrations, approve_steps=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    summary = "; ".join(exec_result.summaries) if exec_result.summaries else "No approved steps were ready to run."
    try:
        await doc_svc.add_message(
            thread_id, "assistant", f"Ran the approved onboarding steps: {summary}",
            metadata={"huume_event": "plan_executed", "offer_id": offer_id},
        )
    except Exception:
        logger.warning("huume: failed to post plan-execution summary message for thread %s", thread_id, exc_info=True)

    return {"plan": exec_result.plan, "summary": summary, "offer_id": offer_id}


@router.get("/threads/{thread_id}/huume/record")
async def get_huume_record(
    thread_id: UUID,
    record_type: str = Query(...),
    record_id: str = Query(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Panel-facing fetch for `show_record` — the admin's own auth, not the
    model's. Re-checks the record type's own feature flag (the mount only
    gates `huume`+`matcha_work`), since a flag flipped off after Huume staged
    a record must not leave it fetchable from the panel."""
    thread, caller_company_id = await _get_owned_thread(thread_id, current_user)
    company_id = thread["company_id"]

    # _get_owned_thread's access check (doc_svc.get_thread) also admits
    # thread/project collaborators from OTHER companies — fine for chat
    # access, but this endpoint returns incident/ER/employee/credential
    # records scoped to the THREAD's company, not the caller's. Without this,
    # an outside-tenant collaborator could pass any record_id and read
    # another tenant's incident narratives, witnesses, and employee PII.
    if caller_company_id != company_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    required = record_view.RECORD_REQUIRED_FEATURE.get(record_type)
    if required is None:
        raise HTTPException(status_code=404, detail="Unknown record type")

    features, _ = await huume_store.get_thread_features_and_integrations(company_id)
    if not features.get(required):
        raise HTTPException(status_code=403, detail=f"'{required}' isn't enabled for this company.")

    view = await record_view.get_record_view(company_id=company_id, record_type=record_type, record_id=record_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return view


@router.delete("/threads/{thread_id}/huume/record")
async def close_huume_record(
    thread_id: UUID,
    record_type: str = Query(...),
    record_id: str = Query(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Drop one entry from the panel's open-record working set
    (`current_state.huume_records`) — the `×` on a record tab. No feature
    re-check: removing a stale entry must stay possible even after the
    record type's flag has been flipped off."""
    thread, caller_company_id = await _get_owned_thread(thread_id, current_user)
    company_id = thread["company_id"]
    if caller_company_id != company_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        records = await huume_store.update_huume_records(
            thread_id, lambda current: record_view.remove_open_record(current, record_type=record_type, record_id=record_id),
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"records": records}
