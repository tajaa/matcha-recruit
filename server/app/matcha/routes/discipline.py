"""Platform Discipline Engine API.

Mounted at `/api/discipline`, gated by `require_feature("discipline")`.
Drives the escalation engine, signature workflow (digital / refused /
physical), audit log, and per-company policy mapping.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Body
from pydantic import BaseModel, Field

from ...database import get_connection
from ...core.dependencies import get_current_user
from ...core.models.auth import CurrentUser
from ...core.services.storage import get_storage
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import discipline_ai
from ..services import discipline_compliance
from ..services import discipline_engine
from ..services import discipline_notifications
from ..services.discipline_pdf import render_discipline_letter
from ..services.signature_provider import (
    get_signature_provider,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter()
public_router = APIRouter()


# ── Pydantic models ─────────────────────────────────────────────────────

class RecommendRequest(BaseModel):
    employee_id: UUID
    infraction_type: str
    severity: str = Field(..., pattern="^(minor|moderate|severe|immediate_written)$")


class IssueRequest(BaseModel):
    employee_id: UUID
    infraction_type: str
    severity: str = Field(..., pattern="^(minor|moderate|severe|immediate_written)$")
    discipline_type: str = Field(..., pattern="^(verbal_warning|written_warning|pip|final_warning|suspension)$")
    issued_date: date
    description: Optional[str] = None
    expected_improvement: Optional[str] = None
    review_date: Optional[date] = None
    documents: Optional[list[Any]] = None
    override_level: bool = False
    override_reason: Optional[str] = None
    # When the conduct happened — distinct from `issued_date` (when HR wrote the
    # letter). The compliance gate tests these against protected leave, so an
    # empty list means the leave overlap check has nothing to test.
    occurrence_dates: list[date] = Field(default_factory=list)
    situation: Optional[str] = None
    advisory_ack_reason: Optional[str] = None


class DraftRequest(BaseModel):
    employee_id: UUID
    situation: str = Field(..., min_length=20)
    infraction_type: Optional[str] = None
    severity: Optional[str] = None


class RefuseRequest(BaseModel):
    notes: str = Field(..., min_length=1)


class PolicyUpsertRequest(BaseModel):
    label: Optional[str] = None
    default_severity: str = Field("moderate", pattern="^(minor|moderate|severe|immediate_written)$")
    lookback_months_minor: int = Field(6, ge=1, le=120)
    lookback_months_moderate: int = Field(9, ge=1, le=120)
    lookback_months_severe: int = Field(12, ge=1, le=120)
    auto_to_written: bool = False
    notify_grandparent_manager: bool = True


# ── Helpers ─────────────────────────────────────────────────────────────

def _json_safe(v: Any) -> Any:
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, list):
        return [_json_safe(i) for i in v]
    if isinstance(v, dict):
        return {k: _json_safe(i) for k, i in v.items()}
    return v


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert UUIDs/dates/datetimes to JSON-friendly forms, recursively.

    Recursion matters now that records carry `occurrence_dates` (a list of
    dates) and `compliance_check` (a nested dict) — a shallow pass leaves raw
    date objects inside them and the response fails to encode.
    """
    if record is None:
        return None  # type: ignore
    return {k: _json_safe(v) for k, v in record.items()}


async def _ensure_record_in_company(
    conn, discipline_id: UUID, company_id: UUID
) -> dict[str, Any]:
    record = await discipline_engine.fetch_record(conn, discipline_id)
    if not record:
        raise HTTPException(status_code=404, detail="Discipline record not found")
    if record["company_id"] != company_id:
        raise HTTPException(status_code=404, detail="Discipline record not found")
    return record


async def _load_employee(conn, employee_id: UUID, company_id: UUID) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT id,
               TRIM(BOTH ' ' FROM COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) AS name,
               first_name, last_name, email, job_title, manager_id, org_id
        FROM employees
        WHERE id = $1 AND org_id = $2
        """,
        employee_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Employee not found in this company")
    return dict(row)


async def _load_company(conn, company_id: UUID) -> dict[str, Any]:
    row = await conn.fetchrow(
        "SELECT id, name, logo_url FROM companies WHERE id = $1",
        company_id,
    )
    return dict(row) if row else {"id": company_id, "name": "Company", "logo_url": None}


async def _load_issuer(conn, user_id: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT id, email FROM users WHERE id = $1",
        user_id,
    )
    if not row:
        return None
    return {"name": row["email"], "title": "Human Resources"}


# ── Endpoints ───────────────────────────────────────────────────────────

@router.post("/recommend")
async def recommend(
    body: RecommendRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        await _load_employee(conn, body.employee_id, company_id)
        result = await discipline_engine.recommend_next_discipline(
            conn,
            employee_id=body.employee_id,
            company_id=company_id,
            infraction_type=body.infraction_type,
            severity=body.severity,
        )
    return result


@router.get("/compliance-check")
async def compliance_check(
    employee_id: UUID,
    infraction_type: str,
    occurrence_dates: str = "",
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Preview the compliance verdict before issuing. Deterministic half only.

    The frontend calls this live as HR fills the form so a block surfaces before
    they've written a letter they can't issue. It is a preview, not the gate —
    `POST /records` re-runs the same check server-side and is the only thing that
    decides. A stale or spoofed preview therefore can't let anything through.
    """
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    dates: list[date] = []
    for chunk in (occurrence_dates or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            dates.append(date.fromisoformat(chunk))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid occurrence date '{chunk}' — expected YYYY-MM-DD",
            )

    async with get_connection() as conn:
        await _load_employee(conn, employee_id, company_id)
        verdict = await discipline_compliance.check_discipline_compliance(
            conn,
            company_id=company_id,
            employee_id=employee_id,
            infraction_type=infraction_type,
            occurrence_dates=dates,
        )
    return verdict


@router.post("/ai/draft")
async def draft_letter(
    body: DraftRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Draft the corrective-action letter from HR's account of what happened.

    Grounded in the company's own records; hallucinated citations are dropped by
    the shared gate. The draft is a starting point for HR to edit — nothing is
    written to the record until they issue.
    """
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        await _load_employee(conn, body.employee_id, company_id)
        draft = await discipline_ai.draft_discipline_letter(
            conn,
            company_id=company_id,
            employee_id=body.employee_id,
            situation=body.situation,
            infraction_type=body.infraction_type,
            severity=body.severity,
        )
    if not draft.get("available"):
        raise HTTPException(
            status_code=503,
            detail="The AI drafting service is unavailable right now. Write the letter manually — discipline can still be issued.",
        )
    return draft


@router.post("/records")
async def issue_record(
    body: IssueRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        await _load_employee(conn, body.employee_id, company_id)

        # The gate runs here, server-side, on every issue — never trusting what
        # the client previewed. A block is a statutory prohibition, so there is
        # no acknowledge-and-proceed path for it: the write is refused.
        verdict = await discipline_compliance.check_discipline_compliance(
            conn,
            company_id=company_id,
            employee_id=body.employee_id,
            infraction_type=body.infraction_type,
            occurrence_dates=body.occurrence_dates,
        )

        if not verdict["blocks"]:
            # Only worth spending a Gemini call once the action is otherwise viable.
            ai_advisories = await discipline_ai.review_final_text(
                conn,
                company_id=company_id,
                employee_id=body.employee_id,
                situation=body.situation,
                description=body.description,
                expected_improvement=body.expected_improvement,
                infraction_type=body.infraction_type,
                severity=body.severity,
                discipline_type=body.discipline_type,
                deterministic_verdict=verdict,
            )
            verdict["advisories"].extend(ai_advisories)

    if verdict["blocks"]:
        raise HTTPException(
            status_code=422,
            detail={"code": "compliance_block", "verdict": verdict},
        )

    if verdict["advisories"] and not (body.advisory_ack_reason or "").strip():
        raise HTTPException(
            status_code=409,
            detail={"code": "compliance_advisories", "verdict": verdict},
        )

    try:
        record = await discipline_engine.issue_discipline_with_supersede(
            actor_user_id=current_user.id,
            company_id=company_id,
            employee_id=body.employee_id,
            infraction_type=body.infraction_type,
            severity=body.severity,
            discipline_type=body.discipline_type,
            issued_date=body.issued_date,
            description=body.description,
            expected_improvement=body.expected_improvement,
            review_date=body.review_date,
            documents=body.documents,
            override_level=body.override_level,
            override_reason=body.override_reason,
            occurrence_dates=body.occurrence_dates,
            situation_narrative=body.situation,
            compliance_check=verdict,
            advisory_ack_reason=body.advisory_ack_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Move from draft → pending_meeting on issue (HR begins workflow immediately)
    async with get_connection() as conn:
        record = await discipline_engine.transition_status(
            conn, record["id"], expected_from=["draft"], to="pending_meeting",
        ) or record
        await discipline_engine.write_audit(
            conn, record["id"], current_user.id, "issued",
            details={"discipline_type": record["discipline_type"]},
        )

    # Notify
    try:
        mapping = None
        async with get_connection() as conn:
            mapping = await discipline_engine.get_policy_mapping(
                conn, company_id, record["infraction_type"]
            )
        await discipline_notifications.dispatch(
            record=record,
            action="discipline_issued",
            notify_grandparent=bool(mapping.get("notify_grandparent_manager", True)),
            skip_user_id=current_user.id,
        )
    except Exception:
        logger.exception("[discipline] failed to dispatch issued notifications")

    return _serialize_record(record)


@router.get("/records/employee/{employee_id}")
async def list_for_employee(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        await _load_employee(conn, employee_id, company_id)
        records = await discipline_engine.list_records_for_employee(conn, employee_id)
    return [_serialize_record(r) for r in records if r["company_id"] == company_id]


@router.get("/records")
async def list_for_company(
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        records = await discipline_engine.list_records_for_company(
            conn, company_id, status_filter=status,
        )
    return [_serialize_record(r) for r in records]


@router.get("/records/{discipline_id}")
async def get_record(
    discipline_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        record = await _ensure_record_in_company(conn, discipline_id, company_id)
    return _serialize_record(record)


@router.get("/records/{discipline_id}/audit-log")
async def get_audit_log(
    discipline_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        await _ensure_record_in_company(conn, discipline_id, company_id)
        log = await discipline_engine.list_audit_log(conn, discipline_id)
    return [_serialize_record(r) for r in log]


@router.patch("/records/{discipline_id}/meeting-held")
async def mark_meeting_held(
    discipline_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        record = await _ensure_record_in_company(conn, discipline_id, company_id)
        if record["meeting_held_at"] is not None:
            return _serialize_record(record)  # idempotent
        updated = await discipline_engine.transition_status(
            conn, discipline_id,
            expected_from=["draft", "pending_meeting"],
            to="pending_signature",
            extra_sets={"meeting_held_at": datetime.now(timezone.utc)},
        )
        if not updated:
            raise HTTPException(
                status_code=409,
                detail="Record is not in draft or pending_meeting state",
            )
        await discipline_engine.write_audit(
            conn, discipline_id, current_user.id, "meeting_held",
        )
    return _serialize_record(updated)


@router.post("/records/{discipline_id}/signature/request")
async def request_signature(
    discipline_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        record = await _ensure_record_in_company(conn, discipline_id, company_id)
        if record["status"] != "pending_signature":
            raise HTTPException(
                status_code=409,
                detail="Record must have meeting_held marked before signature can be requested",
            )
        employee = await _load_employee(conn, record["employee_id"], company_id)
        company = await _load_company(conn, company_id)
        issuer = await _load_issuer(conn, record["issued_by"])

    pdf_bytes = await render_discipline_letter(record, employee, company, issuer)

    provider = get_signature_provider()
    subject = f"{(employee.get('name') or 'Employee')} — {record['discipline_type'].replace('_', ' ').title()}"
    send_result = await provider.send(
        recipient_email=employee["email"],
        recipient_name=employee.get("name"),
        document_pdf=pdf_bytes,
        subject=subject,
        metadata={"discipline_id": str(discipline_id), "company_id": str(company_id)},
    )

    async with get_connection() as conn:
        updated = await discipline_engine.update_signature_status(
            conn, discipline_id,
            signature_status="requested",
            extra_sets={
                "signature_envelope_id": send_result.envelope_id,
                "signature_requested_at": datetime.now(timezone.utc),
            },
        )
        await discipline_engine.write_audit(
            conn, discipline_id, current_user.id, "signature_requested",
            details={"envelope_id": send_result.envelope_id},
        )

    try:
        await discipline_notifications.dispatch(
            record=updated,
            action="discipline_signature_requested",
            skip_user_id=current_user.id,
        )
    except Exception:
        logger.exception("[discipline] notification dispatch failed for signature_requested")

    return _serialize_record(updated)


@router.post("/records/{discipline_id}/signature/refuse")
async def refuse_signature(
    discipline_id: UUID,
    body: RefuseRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        record = await _ensure_record_in_company(conn, discipline_id, company_id)
        if record["status"] not in ("pending_signature", "pending_meeting", "draft"):
            raise HTTPException(
                status_code=409,
                detail="Record is not in a state where refusal can be recorded",
            )

        await discipline_engine.update_signature_status(
            conn, discipline_id,
            signature_status="refused",
            extra_sets={"signature_completed_at": datetime.now(timezone.utc)},
        )
        updated = await discipline_engine.transition_status(
            conn, discipline_id,
            expected_from=["pending_signature", "pending_meeting", "draft"],
            to="active",
        )
        await discipline_engine.write_audit(
            conn, discipline_id, current_user.id, "refused",
            details={"notes": body.notes},
        )

    try:
        await discipline_notifications.dispatch(
            record=updated,
            action="discipline_refused",
            skip_user_id=current_user.id,
        )
    except Exception:
        logger.exception("[discipline] notification dispatch failed for refused")

    return _serialize_record(updated)


@router.post("/records/{discipline_id}/signature/upload-physical")
async def upload_physical_signature(
    discipline_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    if file.content_type and "pdf" not in file.content_type.lower():
        raise HTTPException(status_code=400, detail="File must be a PDF")

    storage = get_storage()
    storage_path = await storage.upload_file(
        contents,
        filename=f"discipline-{discipline_id}-signed.pdf",
        prefix="discipline",
        content_type="application/pdf",
    )

    async with get_connection() as conn:
        await _ensure_record_in_company(conn, discipline_id, company_id)
        await discipline_engine.update_signature_status(
            conn, discipline_id,
            signature_status="physical_uploaded",
            extra_sets={
                "signed_pdf_storage_path": storage_path,
                "signature_completed_at": datetime.now(timezone.utc),
            },
        )
        updated = await discipline_engine.transition_status(
            conn, discipline_id,
            expected_from=["pending_signature", "pending_meeting", "draft"],
            to="active",
        )
        await discipline_engine.write_audit(
            conn, discipline_id, current_user.id, "physical_uploaded",
            details={"storage_path": storage_path},
        )

    try:
        await discipline_notifications.dispatch(
            record=updated,
            action="discipline_physical_uploaded",
            skip_user_id=current_user.id,
        )
    except Exception:
        logger.exception("[discipline] notification dispatch failed for physical_uploaded")

    return _serialize_record(updated)


@router.get("/records/{discipline_id}/letter")
async def download_letter(
    discipline_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Render the discipline letter PDF for download (used for in-person signing)."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    from fastapi.responses import Response

    async with get_connection() as conn:
        record = await _ensure_record_in_company(conn, discipline_id, company_id)
        employee = await _load_employee(conn, record["employee_id"], company_id)
        company = await _load_company(conn, company_id)
        issuer = await _load_issuer(conn, record["issued_by"])

    pdf_bytes = await render_discipline_letter(record, employee, company, issuer)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="discipline-{discipline_id}.pdf"',
        },
    )


@public_router.post("/signature/webhook")
async def signature_webhook(request: Request):
    """Provider webhook receiver. Verifies HMAC, marks record as signed."""
    raw = await request.body()
    sig_header = (
        request.headers.get("X-Docuseal-Signature")
        or request.headers.get("X-DocuSeal-Signature")
        or request.headers.get("X-Signature")
        or ""
    )

    provider = get_signature_provider()
    if not sig_header or not verify_webhook_signature(provider, raw, sig_header):
        logger.warning("[discipline_webhook] HMAC verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = (
        payload.get("event_type")
        or payload.get("type")
        or payload.get("event")
        or ""
    ).lower()
    submission = payload.get("data") or payload.get("submission") or payload
    envelope_id = (
        str(submission.get("submission_id") or submission.get("id") or "")
        if isinstance(submission, dict) else ""
    )

    if not envelope_id:
        logger.warning("[discipline_webhook] no submission id in payload: %s", payload)
        return {"ok": True}

    async with get_connection() as conn:
        record = await discipline_engine.fetch_record_by_envelope(conn, envelope_id)
    if not record:
        logger.warning("[discipline_webhook] no record for envelope %s", envelope_id)
        return {"ok": True}

    is_completed = "complete" in event_type or "signed" in event_type
    is_declined = "decline" in event_type or "refus" in event_type or "expir" in event_type

    if is_completed:
        signed_pdf = None
        try:
            signed_pdf = await provider.fetch_signed_pdf(envelope_id)
        except Exception:
            logger.exception("[discipline_webhook] fetch_signed_pdf failed for %s", envelope_id)

        storage_path = None
        if signed_pdf:
            try:
                storage = get_storage()
                storage_path = await storage.upload_file(
                    signed_pdf,
                    filename=f"discipline-{record['id']}-signed.pdf",
                    prefix="discipline",
                    content_type="application/pdf",
                )
            except Exception:
                logger.exception("[discipline_webhook] failed to store signed PDF")

        async with get_connection() as conn:
            extra: dict[str, Any] = {"signature_completed_at": datetime.now(timezone.utc)}
            if storage_path:
                extra["signed_pdf_storage_path"] = storage_path
            await discipline_engine.update_signature_status(
                conn, record["id"], signature_status="signed", extra_sets=extra,
            )
            updated = await discipline_engine.transition_status(
                conn, record["id"],
                expected_from=["pending_signature", "pending_meeting", "draft"],
                to="active",
            ) or record
            await discipline_engine.write_audit(
                conn, record["id"], None, "signed",
                details={"envelope_id": envelope_id, "storage_path": storage_path},
            )

        try:
            await discipline_notifications.dispatch(record=updated, action="discipline_signed")
        except Exception:
            logger.exception("[discipline_webhook] notification dispatch failed for signed")

    elif is_declined:
        async with get_connection() as conn:
            await discipline_engine.update_signature_status(
                conn, record["id"], signature_status="refused",
                extra_sets={"signature_completed_at": datetime.now(timezone.utc)},
            )
            updated = await discipline_engine.transition_status(
                conn, record["id"],
                expected_from=["pending_signature", "pending_meeting", "draft"],
                to="active",
            ) or record
            await discipline_engine.write_audit(
                conn, record["id"], None, "refused",
                details={"envelope_id": envelope_id, "reason": event_type},
            )
        try:
            await discipline_notifications.dispatch(record=updated, action="discipline_refused")
        except Exception:
            logger.exception("[discipline_webhook] notification dispatch failed for refused")

    else:
        logger.info("[discipline_webhook] unhandled event_type=%s", event_type)

    return {"ok": True}


# ── Policy mapping ──────────────────────────────────────────────────────

@router.get("/policies")
async def list_policies(
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        rows = await discipline_engine.list_policy_mappings(conn, company_id)
    return [_serialize_record(r) for r in rows]


@router.put("/policies/{infraction_type}")
async def upsert_policy(
    infraction_type: str,
    body: PolicyUpsertRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        await discipline_engine.ensure_default_policy_mapping(conn, company_id)
        row = await discipline_engine.upsert_policy_mapping(
            conn, company_id, infraction_type, body.model_dump(),
        )
    return _serialize_record(row)
