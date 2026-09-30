"""HR cases routes — the dedicated HR Cases page on business /work.

Every route requires HR access (`services/hr_cases/access.has_hr_access`:
Work admin, or READ on Drive's HR / Discipline folder); anyone else gets 404
on reads so the existence of a case isn't disclosed. Gated on `hr_cases`
(+ the package-level `matcha_work` gate); business workspaces only.

Static paths (`/hr-cases/access`, `/hr-cases/settings`) are declared before
`/hr-cases/{case_id}`.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, require_feature, resolve_accessible_company_scope
from app.matcha.services.hr_cases import case_service, stages
from app.matcha.services.hr_cases.access import has_hr_access
from app.matcha.services.hr_cases.case_service import CaseError

router = APIRouter(prefix="/hr-cases", dependencies=[Depends(require_feature("hr_cases"))])


class CaseOpen(BaseModel):
    incident_id: UUID


class CaseDismiss(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


class SettingsUpdate(BaseModel):
    triage_min_confidence: Optional[float] = Field(None, ge=0.3, le=0.95)


async def _business_company(current_user: CurrentUser) -> UUID:
    # A platform admin has no company: scope resolution would drop them into
    # the oldest tenant as its Work admin, i.e. with HR access to its cases.
    if current_user.role == "admin":
        raise HTTPException(status_code=403, detail="HR cases are only available inside a company workspace")
    scope = await resolve_accessible_company_scope(current_user)
    company_id = scope.get("company_id")
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        is_personal = await conn.fetchval(
            "SELECT COALESCE(is_personal, false) FROM companies WHERE id = $1", company_id,
        )
    if is_personal:
        raise HTTPException(status_code=403, detail="HR cases are only available in business workspaces")
    return company_id


async def _require_hr(conn, current_user: CurrentUser, company_id: UUID) -> None:
    if not await has_hr_access(conn, user=current_user, company_id=company_id):
        raise HTTPException(status_code=404, detail="Not found")


def _raise(exc: CaseError):
    raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/access")
async def get_access(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        return {"hr_access": await has_hr_access(conn, user=current_user, company_id=company_id)}


@router.get("/settings")
async def get_settings(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        await _require_hr(conn, current_user, company_id)
        settings = await case_service.get_settings(conn, company_id)
    return {
        "triage_min_confidence": float(settings["triage_min_confidence"]),
        "filename_template": settings["filename_template"],
    }


@router.put("/settings")
async def update_settings(body: SettingsUpdate, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        await _require_hr(conn, current_user, company_id)
        if body.triage_min_confidence is not None:
            await conn.execute(
                """
                INSERT INTO hr_case_settings (company_id, triage_min_confidence, updated_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (company_id) DO UPDATE
                SET triage_min_confidence = EXCLUDED.triage_min_confidence,
                    updated_by = EXCLUDED.updated_by, updated_at = NOW()
                """,
                company_id, body.triage_min_confidence, current_user.id,
            )
        settings = await case_service.get_settings(conn, company_id)
    return {
        "triage_min_confidence": float(settings["triage_min_confidence"]),
        "filename_template": settings["filename_template"],
    }


@router.get("")
async def list_cases(include_closed: bool = False, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        await _require_hr(conn, current_user, company_id)
        cases = await case_service.list_cases(conn, company_id=company_id, include_closed=include_closed)
    return {
        "columns": [{"key": key, "label": label, "stages": list(st)} for key, label, st in stages.COLUMNS],
        "cases": cases,
    }


@router.post("")
async def open_case(body: CaseOpen, current_user: CurrentUser = Depends(require_admin_or_client)):
    """Open a case on an incident by hand (HR decided without a flag)."""
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        await _require_hr(conn, current_user, company_id)
        incident = await conn.fetchrow(
            "SELECT id, created_by, reported_by_email, involved_employee_ids FROM ir_incidents "
            "WHERE id = $1 AND company_id = $2",
            body.incident_id, company_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="That incident doesn't exist.")
        from app.matcha.services.hr_cases.notifications import resolve_gm_user_id
        from app.matcha.services.hr_cases.triage import _single_involved_employee

        gm = await resolve_gm_user_id(conn, company_id=company_id, incident=dict(incident))
        try:
            case, created = await case_service.open_case(
                conn, company_id=company_id, origin="manual", incident_id=body.incident_id,
                gm_user_id=gm, opened_by=current_user.id,
                employee_id=_single_involved_employee(dict(incident)),
            )
        except CaseError as exc:
            _raise(exc)
    return {"case": case, "created": created}


@router.get("/{case_id}")
async def get_case(case_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        await _require_hr(conn, current_user, company_id)
        try:
            return await case_service.get_case(conn, company_id=company_id, case_id=case_id, with_events=True)
        except CaseError as exc:
            _raise(exc)


@router.post("/{case_id}/dismiss")
async def dismiss_case(case_id: UUID, body: CaseDismiss, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        await _require_hr(conn, current_user, company_id)
        try:
            return await case_service.dismiss_case(
                conn, company_id=company_id, case_id=case_id, actor_user_id=current_user.id, reason=body.reason,
            )
        except CaseError as exc:
            _raise(exc)
