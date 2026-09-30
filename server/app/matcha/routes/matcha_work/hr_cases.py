"""HR cases routes — the dedicated HR Cases page on business /work.

Every route requires HR access (`services/hr_cases/access.has_hr_access`:
Work admin, or READ on Drive's HR / Discipline folder); anyone else gets 404
on reads so the existence of a case isn't disclosed. Gated on `hr_cases`
(+ the package-level `matcha_work` gate); business workspaces only.

Two audiences:
  - HR routes call `_require_hr` (list, detail, settings, open, dismiss,
    decision).
  - Manager routes (`/mine`, `/employees`, `/incidents`, `/drafts`,
    `/{case_id}/delivered`, `/{case_id}/draft`) authorize in
    `services/hr_cases/workflow.py`: HR, or the case's own manager. A manager
    only ever receives `workflow.manager_view`, never the HR case record.

Static paths are declared before `/hr-cases/{case_id}`.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.models.auth import CurrentUser
from app.core.services.redis_cache import check_rate_limit
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, require_business_company, require_feature
from app.matcha.services.hr_cases import case_service, stages, workflow
from app.matcha.services.hr_cases.access import can_change_hr_settings, has_hr_access
from app.matcha.services.hr_cases.case_service import CaseError

router = APIRouter(prefix="/hr-cases", dependencies=[Depends(require_feature("hr_cases"))])


class CaseOpen(BaseModel):
    incident_id: UUID


class CaseDismiss(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


class CaseDecision(BaseModel):
    decision: Literal["approve", "request_changes"]
    reason: Optional[str] = Field(None, max_length=2000)


class Delivered(BaseModel):
    delivered_on: Optional[date] = None


DRAFT_LIMIT = (30, 3600)  # per user per hour: each draft runs a model review


class SettingsUpdate(BaseModel):
    triage_min_confidence: Optional[float] = Field(None, ge=0.3, le=0.95)


async def _business_company(current_user: CurrentUser) -> UUID:
    return await require_business_company(current_user, product="HR cases")


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
        if not await can_change_hr_settings(conn, user=current_user, company_id=company_id):
            raise HTTPException(status_code=403, detail="Only a Work admin or someone who manages the HR folder can change HR settings.")
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


# ── Manager-facing (authorized in workflow.py, not by HR access) ───────


@router.get("/mine")
async def my_cases(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        return {"cases": await workflow.list_for_manager(conn, company_id=company_id, user_id=current_user.id)}


@router.get("/employees")
async def search_employees(
    q: Optional[str] = Query(None, max_length=100),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _business_company(current_user)
    term = (q or "").strip()
    pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, NULLIF(TRIM(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')), '') AS name,
                   job_title
            FROM employees
            WHERE org_id = $1 AND termination_date IS NULL
              AND ($2 = '' OR (COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) ILIKE $3 ESCAPE '\\')
            ORDER BY last_name NULLS LAST, first_name
            LIMIT 20
            """,
            company_id, term, pattern,
        )
    return {"employees": [dict(r) for r in rows]}


@router.get("/incidents")
async def recent_incidents(
    q: Optional[str] = Query(None, max_length=100),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Incidents a write-up can be linked to: any, for HR; otherwise only the
    ones the caller reported (the same rule `workflow.submit_draft` enforces)."""
    from app.matcha.services.hr_cases.notifications import resolve_gm_user_id

    company_id = await _business_company(current_user)
    term = (q or "").strip()
    pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    async with get_connection() as conn:
        is_hr = await has_hr_access(conn, user=current_user, company_id=company_id)
        rows = await conn.fetch(
            """
            SELECT id, incident_number, title, occurred_at, created_by, reported_by_email FROM ir_incidents
            WHERE company_id = $1
              AND ($2 = '' OR title ILIKE $3 ESCAPE '\\' OR incident_number ILIKE $3 ESCAPE '\\')
              AND ($4 OR created_by = $5 OR lower(reported_by_email) = lower($6))
            ORDER BY occurred_at DESC NULLS LAST
            LIMIT 20
            """,
            company_id, term, pattern, is_hr, current_user.id, current_user.email,
        )
        if not is_hr:
            rows = [r for r in rows
                    if await resolve_gm_user_id(conn, company_id=company_id, incident=dict(r)) == current_user.id]
    return {"incidents": [
        {"id": r["id"], "incident_number": r["incident_number"], "title": r["title"], "occurred_at": r["occurred_at"]}
        for r in rows
    ]}


@router.post("/drafts", status_code=201)
async def submit_draft(
    employee_id: UUID = Form(...),
    action_type: str = Form(...),
    infraction_type: str = Form(...),
    occurrence_dates: str = Form(""),
    case_id: Optional[UUID] = Form(None),
    incident_id: Optional[UUID] = Form(None),
    drive_file_id: Optional[UUID] = Form(None),
    google_url: Optional[str] = Form(None, max_length=2000),
    file: Optional[UploadFile] = File(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """A manager (or HR) sends a write-up: an uploaded file, a file already
    in Drive the sender can read, or a Google Doc link."""
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive import google_drive_service as gdrive
    from app.matcha.services.drive.drive_service import DriveError
    from app.matcha.services.drive.google_drive_service import GoogleDriveError, GoogleDriveService

    company_id = await _business_company(current_user)
    sources = [x for x in (file, drive_file_id, (google_url or "").strip() or None) if x]
    if len(sources) != 1:
        raise HTTPException(status_code=400, detail="Send exactly one of: a file, a Drive file, or a Google Doc link.")
    await check_rate_limit(str(current_user.id), "hr_case_draft", *DRAFT_LIMIT)
    try:
        dates = workflow.parse_occurrence_dates(occurrence_dates.split(","))
    except CaseError as exc:
        _raise(exc)

    source, source_ref = "upload", None
    try:
        if file is not None:
            data = await file.read(drive_service.MAX_FILE_BYTES + 1)
            prepared = await drive_service.prepare_file(file.filename or "draft", data)
        elif drive_file_id is not None:
            async with get_connection() as conn:
                actor = await drive_service.load_actor(conn, user=current_user, company_id=company_id)
                meta, data = await drive_service.read_file_bytes(conn, company_id=company_id, file_id=drive_file_id, actor=actor)
            prepared = await drive_service.prepare_file(meta["filename"], data)
            source_ref = f"drive:{drive_file_id}"
        else:
            file_id = gdrive.parse_file_id(google_url or "")
            if not file_id:
                raise HTTPException(status_code=400, detail="Paste a link to a Google Doc or Drive file.")
            fetched = await GoogleDriveService(current_user.id).fetch_file(file_id)
            prepared = await drive_service.prepare_file(fetched.name, fetched.data)
            source, source_ref = "google_drive", fetched.file_id
    except DriveError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    except GoogleDriveError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc

    async with get_connection() as conn:
        is_hr = await has_hr_access(conn, user=current_user, company_id=company_id)
    # submit_draft takes its own short connections: its model review and
    # notification emails must not pin a pool connection.
    try:
        result = await workflow.submit_draft(
            get_connection, company_id=company_id, actor_user_id=current_user.id, actor_is_hr=is_hr,
            prepared=prepared, employee_id=employee_id, action_type=action_type,
            infraction_type=infraction_type, occurrence_dates=dates,
            case_id=case_id, incident_id=incident_id, source=source, source_ref=source_ref,
        )
    except CaseError as exc:
        _raise(exc)
    except DriveError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    return {"status": result["status"], "case": result["manager_view"]}


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


@router.post("/{case_id}/decision")
async def decide_case(case_id: UUID, body: CaseDecision, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        await _require_hr(conn, current_user, company_id)
        try:
            return await workflow.decide(
                conn, company_id=company_id, case_id=case_id, actor_user_id=current_user.id,
                decision=body.decision, reason=body.reason,
            )
        except CaseError as exc:
            _raise(exc)


@router.post("/{case_id}/delivered")
async def mark_delivered(case_id: UUID, body: Delivered, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        is_hr = await has_hr_access(conn, user=current_user, company_id=company_id)
        try:
            case = await workflow.mark_delivered(
                conn, company_id=company_id, case_id=case_id, actor_user_id=current_user.id,
                actor_is_hr=is_hr, delivered_on=body.delivered_on,
            )
        except CaseError as exc:
            _raise(exc)
    return case if is_hr else workflow.manager_view(case)


@router.get("/{case_id}/draft")
async def draft_download(case_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    """Short-lived link to the case's current draft — HR or the case's manager.
    Goes through Drive's system path so the HR-space download is audited."""
    from app.matcha.services.drive import drive_service
    from app.matcha.services.drive.drive_service import DriveError

    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        is_hr = await has_hr_access(conn, user=current_user, company_id=company_id)
        try:
            case = await workflow.load_for_actor(conn, company_id=company_id, case_id=case_id,
                                                 actor_user_id=current_user.id, actor_is_hr=is_hr)
        except CaseError as exc:
            _raise(exc)
        if not case.get("draft_file_id"):
            raise HTTPException(status_code=404, detail="There's no draft on this case yet.")
        try:
            return await drive_service.presign_download(
                conn, company_id=company_id, file_id=case["draft_file_id"], actor=None,
                on_behalf_of=current_user.id, audit_details={"via": "hr_case", "case_id": str(case_id)},
            )
        except DriveError as exc:
            detail = "The draft file is no longer available." if exc.status == 404 else exc.detail
            raise HTTPException(status_code=exc.status, detail=detail) from exc
