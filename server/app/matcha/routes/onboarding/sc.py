"""Authenticated Matcha S&C account-setup endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_client
from app.matcha.models.sc_onboarding import (
    ScOnboardingComplete,
    ScOnboardingCsvParse,
    ScOnboardingResult,
    ScOnboardingStatus,
)
from app.matcha.services.employees.roster_csv import RosterCsvError
from app.matcha.services.sc_onboarding import (
    ScOnboardingAccessError,
    ScOnboardingError,
    complete_sc_onboarding,
    get_sc_onboarding_status,
    parse_employees_csv,
    parse_locations_csv,
)

# Comfortably above 500 rows of either file; the row caps are the real limit.
MAX_CSV_BYTES = 2 * 1024 * 1024

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
    except ValueError as exc:
        # Shared write helpers (credential rules, scheduling) refuse invalid
        # submissions with a bare ValueError. Surfacing that as a 500 would turn
        # an actionable validation refusal into a server_error_reports row.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/csv/{kind}", response_model=ScOnboardingCsvParse)
async def parse_csv(kind: str, file: UploadFile = File(...), current_user=Depends(require_client)):
    """Validate an import file and hand the rows back — nothing is written.

    Parsing lives here, not in the browser, so the wizard cannot accept a file
    that `/complete` would then refuse. The wizard's own guarantee is unchanged:
    these rows sit in the client until the manager approves the final review.
    """
    parser = {"locations": parse_locations_csv, "employees": parse_employees_csv}.get(kind)
    if parser is None:
        raise HTTPException(status_code=404, detail="Unknown import file")
    await _company_id(current_user)

    payload = await file.read(MAX_CSV_BYTES + 1)
    if len(payload) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV file is too large")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 text") from exc

    try:
        return {"rows": parser(text)}
    except RosterCsvError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
