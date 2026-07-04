"""IR Copilot "Request More Info" — admin-side token management.

Admin composes questions (seeded from the Copilot's own open_questions, plus
any custom ones) and emails an outside party a single-use link scoped to one
incident. The public GET/POST pair the link resolves to lives in
`inbound_email.py`, alongside `/report/{token}` and `/intake/{token}`.
"""
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.core.services.email import get_email_service
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client

from ._shared import (
    _build_public_link,
    _get_incident_with_company_check,
    _info_request_effective_status,
    _safe_json_loads,
    log_audit,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_EXPIRY_DAYS = 14


class InfoRequestQuestion(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    source: Literal["copilot", "admin"] = "admin"


class InfoRequestCreate(BaseModel):
    recipient_name: str = Field(..., min_length=1, max_length=255)
    recipient_email: EmailStr
    questions: list[InfoRequestQuestion] = Field(..., min_length=1, max_length=20)
    custom_message: Optional[str] = Field(None, max_length=2000)


def _serialize_info_request(request: Request, row) -> dict:
    return {
        "id": str(row["id"]),
        "recipient_name": row["recipient_name"],
        "recipient_email": row["recipient_email"],
        "questions": _safe_json_loads(row["questions"], []),
        "custom_message": row["custom_message"],
        "responses": _safe_json_loads(row["responses"], None) if row["responses"] else None,
        "status": _info_request_effective_status(row),
        "link": _build_public_link(request, row["token"], "request-info"),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
    }


async def _requester_display_name(conn, current_user) -> str:
    """Best-effort human name for the "X is asking for more info" email line."""
    row = await conn.fetchrow(
        "SELECT name FROM clients WHERE user_id = $1", current_user.id,
    )
    if row and row["name"]:
        return row["name"]
    return current_user.email.split("@")[0]


@router.post("/{incident_id}/info-requests")
async def create_info_request(
    incident_id: UUID,
    body: InfoRequestCreate,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Create an info request, email the recipient, and return the created row.

    The send is awaited (not backgrounded) — the response's `email_sent` flag
    is the admin's only signal that the invite actually went out, so we need
    the result before replying. The DB connection is released before the
    send, though — an external email round-trip has no business pinning a
    pool slot.
    """
    async with get_connection() as conn:
        incident = await _get_incident_with_company_check(
            conn, incident_id, current_user, columns="id, company_id, incident_number",
        )
        company = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", incident["company_id"],
        )
        company_name = (company["name"] if company else None) or "Your company"
        requested_by_name = await _requester_display_name(conn, current_user)

        token = secrets.token_urlsafe(24)
        expires_at = datetime.now(timezone.utc) + timedelta(days=_EXPIRY_DAYS)
        questions_payload = [q.model_dump() for q in body.questions]

        row = await conn.fetchrow(
            """
            INSERT INTO ir_info_requests
                (incident_id, company_id, token, recipient_name, recipient_email,
                 questions, custom_message, requested_by, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
            RETURNING *
            """,
            incident_id,
            incident["company_id"],
            token,
            body.recipient_name.strip(),
            body.recipient_email.strip(),
            json.dumps(questions_payload),
            (body.custom_message.strip() if body.custom_message else None),
            current_user.id,
            expires_at,
        )

    link = _build_public_link(request, token, "request-info")
    sent = False
    try:
        email_service = get_email_service()
        sent = await email_service.send_ir_info_request_email(
            to_email=body.recipient_email,
            to_name=body.recipient_name,
            company_name=company_name,
            incident_number=incident["incident_number"],
            requested_by_name=requested_by_name,
            questions=[q.text for q in body.questions],
            custom_message=(body.custom_message.strip() if body.custom_message else None),
            link=link,
        )
        if not sent:
            logger.warning("[IR] info-request email to %s did not send", body.recipient_email)
    except Exception as e:
        logger.warning("[IR] Failed to send info-request email: %s", e)

    async with get_connection() as conn:
        await log_audit(
            conn, str(incident_id), str(current_user.id), "info_request_created",
            "info_request", str(row["id"]),
            {"recipient_email": body.recipient_email, "email_sent": sent},
        )

    result = _serialize_info_request(request, row)
    result["email_sent"] = sent
    return result


@router.get("/{incident_id}/info-requests")
async def list_info_requests(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """List info requests for an incident, newest first."""
    async with get_connection() as conn:
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")
        rows = await conn.fetch(
            "SELECT * FROM ir_info_requests WHERE incident_id = $1 ORDER BY created_at DESC",
            incident_id,
        )
        return [_serialize_info_request(request, r) for r in rows]


@router.post("/{incident_id}/info-requests/{request_id}/resend")
async def resend_info_request(
    incident_id: UUID,
    request_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Send a fresh token + expiry and only persist it once the email is
    confirmed sent — the old link keeps working if the send fails, rather
    than being burned for nothing. The DB connection is released before the
    send so a slow email provider can't pin a pool slot."""
    async with get_connection() as conn:
        incident = await _get_incident_with_company_check(
            conn, incident_id, current_user, columns="id, company_id, incident_number",
        )
        row = await conn.fetchrow(
            "SELECT * FROM ir_info_requests WHERE id = $1 AND incident_id = $2",
            request_id, incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Info request not found")
        if row["status"] == "submitted":
            raise HTTPException(status_code=400, detail="This request has already been answered")
        if row["status"] == "revoked":
            raise HTTPException(status_code=400, detail="This request has been revoked")

        company = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", incident["company_id"],
        )
        company_name = (company["name"] if company else None) or "Your company"
        requested_by_name = await _requester_display_name(conn, current_user)
        questions = _safe_json_loads(row["questions"], [])

    new_token = secrets.token_urlsafe(24)
    new_expires_at = datetime.now(timezone.utc) + timedelta(days=_EXPIRY_DAYS)
    link = _build_public_link(request, new_token, "request-info")

    try:
        email_service = get_email_service()
        sent = await email_service.send_ir_info_request_email(
            to_email=row["recipient_email"],
            to_name=row["recipient_name"],
            company_name=company_name,
            incident_number=incident["incident_number"],
            requested_by_name=requested_by_name,
            questions=[q["text"] for q in questions],
            custom_message=row["custom_message"],
            link=link,
        )
    except Exception as e:
        logger.warning("[IR] Failed to resend info-request email: %s", e)
        sent = False

    if not sent:
        # Don't burn the old (still-valid) token/link on a failed resend.
        raise HTTPException(status_code=502, detail="Failed to send invite email")

    async with get_connection() as conn:
        # Guard against a concurrent submit/revoke landing between our
        # read above and this write (same race class as revoke below) —
        # only rotate the token if the request is still pending.
        updated = await conn.fetchrow(
            """
            UPDATE ir_info_requests
            SET token = $1, expires_at = $2
            WHERE id = $3 AND status NOT IN ('submitted', 'revoked')
            RETURNING *
            """,
            new_token, new_expires_at, request_id,
        )
        if not updated:
            raise HTTPException(
                status_code=409,
                detail="This request was answered or revoked before the resend completed",
            )

        await log_audit(
            conn, str(incident_id), str(current_user.id), "info_request_resent",
            "info_request", str(request_id), {"recipient_email": updated["recipient_email"]},
        )

    return _serialize_info_request(request, updated)


@router.delete("/{incident_id}/info-requests/{request_id}")
async def revoke_info_request(
    incident_id: UUID,
    request_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Invalidate an unanswered info-request link (e.g. sent to the wrong address)."""
    async with get_connection() as conn:
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")
        exists = await conn.fetchval(
            "SELECT 1 FROM ir_info_requests WHERE id = $1 AND incident_id = $2",
            request_id, incident_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Info request not found")

        # Conditional UPDATE (not SELECT-then-UPDATE) so a concurrent public
        # submission landing between our check and write can't be silently
        # overwritten to 'revoked' with its answers still attached.
        updated = await conn.fetchrow(
            "UPDATE ir_info_requests SET status = 'revoked' "
            "WHERE id = $1 AND status <> 'submitted' RETURNING *",
            request_id,
        )
        if not updated:
            raise HTTPException(status_code=400, detail="This request has already been answered")

        await log_audit(
            conn, str(incident_id), str(current_user.id), "info_request_revoked",
            "info_request", str(request_id), {},
        )

        return _serialize_info_request(request, updated)
