"""Espresso Job search: saved searches, their ranked jobs, and what to do next.

Personal Espresso accounts only (the assistant's rule), Pro and up, with a
monthly allowance of whole searches. The search itself runs in the worker
(`services/matcha_work/job_search/`); these routes start, read, re-rank and
tidy it. Everything is scoped to the caller: another person's ids are 404.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.models.auth import CurrentUser
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.matcha_work.job_search import EmailDraftRequest, JobSearchCreate, JobWeights, LeadPatch
from app.matcha.services.matcha_work.agent_runtime import consent
from app.matcha.services.matcha_work.job_search import enqueue, quota, service

from .assistant import require_personal_workspace

router = APIRouter(
    prefix="/job-searches",
    dependencies=[Depends(require_personal_workspace)],
)


async def _company(current_user: CurrentUser) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No workspace is selected.")
    return company_id


async def _call(operation):
    try:
        return await operation
    except service.JobSearchError as exc:
        raise HTTPException(status_code=exc.code, detail=exc.detail or str(exc)) from exc


@router.get("")
async def list_job_searches(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _company(current_user)
    return {
        "searches": await service.list_searches(current_user.id, company_id),
        "usage": await quota.job_search_usage(current_user.id),
        "consent": {
            "granted": await enqueue.consent_granted(current_user.id),
            "disclosure": consent.disclosure_view(enqueue.ABILITY_KEY),
        },
        # Always: with no listings key a search finds postings on the web.
        # Kept for app builds that hide job search when it is false.
        "available": True,
    }


@router.post("", status_code=202)
async def create_job_search(
    body: JobSearchCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _company(current_user)
    return await _call(enqueue.create_search(current_user, company_id, body))


@router.get("/{search_id}")
async def get_job_search(search_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(service.get_search(search_id, current_user.id))


@router.get("/{search_id}/status")
async def job_search_status(search_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(service.status_view(search_id, current_user.id))


@router.get("/{search_id}/leads/{lead_id}")
async def get_job_lead(
    search_id: UUID, lead_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(service.get_lead(search_id, lead_id, current_user.id))


@router.patch("/{search_id}/leads/{lead_id}")
async def update_job_lead(
    search_id: UUID, lead_id: UUID, body: LeadPatch,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(service.patch_lead(search_id, lead_id, current_user.id, body))


@router.post("/{search_id}/leads/{lead_id}/approach", status_code=202)
async def redraft_job_approach(
    search_id: UUID, lead_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Draft how to approach this job (again). Free; capped per search."""
    return await _call(enqueue.redraft_approach(current_user, search_id, lead_id))


@router.post("/{search_id}/widen", status_code=202)
async def widen_job_search(search_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    """Add the 3/5 matches to a search that showed its 4/5 and 5/5 ones first:
    their postings are read and they rank with the rest. Free, once per
    search; nothing is drafted for them unless asked."""
    return await _call(enqueue.widen(current_user, search_id))


@router.post("/{search_id}/leads/{lead_id}/email-draft")
async def draft_job_email(
    search_id: UUID, lead_id: UUID, body: EmailDraftRequest | None = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Put this job's drafted first message in the caller's Gmail drafts, to
    edit and send from Email. Nothing is sent. Asking again returns the same
    draft while it is still in Gmail. `existing_only` never makes one: a
    draft that left Gmail is a 409 `email_draft_missing`."""
    existing_only = bool(body and body.existing_only)
    return await _call(service.draft_email(search_id, lead_id, current_user.id, existing_only=existing_only))


@router.put("/{search_id}/weights")
async def rerank_job_search(
    search_id: UUID, body: JobWeights,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """New weights and an immediate re-rank. Free: no search is spent."""
    return await _call(service.update_weights(search_id, current_user.id, body))


@router.post("/{search_id}/cancel")
async def cancel_job_search(search_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(service.cancel_search(search_id, current_user.id))


@router.delete("/{search_id}")
async def delete_job_search(search_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(service.delete_search(search_id, current_user.id))
