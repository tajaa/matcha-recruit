"""Authenticated Matcha S&C account-setup endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_client
from app.matcha.models.sc_onboarding import (
    ScOnboardingComplete,
    ScOnboardingResult,
    ScOnboardingStatus,
)
from app.matcha.services.sc_onboarding import (
    ScOnboardingAccessError,
    ScOnboardingError,
    complete_sc_onboarding,
    get_sc_onboarding_status,
)

router = APIRouter()


async def _company_id(current_user) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="A company-admin account is required")
    return company_id


@router.get("/status", response_model=ScOnboardingStatus)
async def status(current_user=Depends(require_client)):
    company_id = await _company_id(current_user)
    try:
        async with get_connection() as conn:
            return await get_sc_onboarding_status(conn, company_id=company_id)
    except ScOnboardingAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/complete", response_model=ScOnboardingResult)
async def complete(body: ScOnboardingComplete, current_user=Depends(require_client)):
    company_id = await _company_id(current_user)
    try:
        async with get_connection() as conn:
            return await complete_sc_onboarding(
                conn,
                company_id=company_id,
                actor_user_id=current_user.id,
                body=body,
            )
    except ScOnboardingAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ScOnboardingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
