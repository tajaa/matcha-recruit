"""Investigation interview endpoints for IR Incidents.

Lets HR/admins schedule witness interviews tied to an incident. Each
interview gets AI-generated questions, an `interviews` row, an
`ir_investigation_interviews` junction row, and a WebSocket auth token.
"""
import json
import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.core.services.email import get_email_service
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.interview import (
    InvestigationInterviewCreate,
    InvestigationInterviewResponse,
    InvestigationInterviewStart,
)

# log_audit currently lives in _legacy.py; will move to _shared.py in step 10.
from ._shared import log_audit

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{incident_id}/investigation-interviews", response_model=InvestigationInterviewStart)
async def create_investigation_interview(
    incident_id: UUID,
    request_body: InvestigationInterviewCreate,
    current_user=Depends(require_admin_or_client),
):
    """Create an investigation interview for an IR incident.

    Generates questions, creates interview + junction row, returns ws_auth_token.
    """
    from app.matcha.services.ir_interview_questions import generate_investigation_questions
    from app.core.services.auth import create_interview_ws_token

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            """
            SELECT id, title, description, incident_type, severity, status, location,
                   occurred_at, witnesses, company_id
            FROM ir_incidents WHERE id = $1
            """,
            incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        if incident["status"] not in ("investigating", "action_required", "reported"):
            raise HTTPException(
                status_code=400,
                detail=f"Incident must be in investigating, action_required, or reported status (current: {incident['status']})",
            )

        prior_transcripts = []
        prior_rows = await conn.fetch(
            """
            SELECT i.transcript
            FROM ir_investigation_interviews irii
            JOIN interviews i ON irii.interview_id = i.id
            WHERE irii.incident_id = $1 AND i.transcript IS NOT NULL
            ORDER BY irii.created_at
            """,
            incident_id,
        )
        prior_transcripts = [r["transcript"] for r in prior_rows]

        settings = get_settings()
        incident_data = {
            "title": incident["title"],
            "description": incident["description"],
            "incident_type": incident["incident_type"],
            "severity": incident["severity"],
            "location": incident["location"],
            "occurred_at": str(incident["occurred_at"]) if incident["occurred_at"] else None,
        }
        questions = await generate_investigation_questions(
            incident=incident_data,
            interviewee_name=request_body.interviewee_name,
            interviewee_role=request_body.interviewee_role,
            prior_transcripts=prior_transcripts if prior_transcripts else None,
            api_key=settings.gemini_api_key,
            model=settings.analysis_model,
        )

        async with conn.transaction():
            interview_row = await conn.fetchrow(
                """
                INSERT INTO interviews (company_id, interview_type, incident_id, er_case_id, interviewee_role, status)
                VALUES ($1, 'investigation', $2, $3, $4, 'pending')
                RETURNING id
                """,
                incident["company_id"],
                incident_id,
                request_body.er_case_id,
                request_body.interviewee_role,
            )
            interview_id = interview_row["id"]

            junction_row = await conn.fetchrow(
                """
                INSERT INTO ir_investigation_interviews
                    (incident_id, interview_id, er_case_id, interviewee_role, interviewee_name, interviewee_email, questions_generated, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
                RETURNING id
                """,
                incident_id,
                interview_id,
                request_body.er_case_id,
                request_body.interviewee_role,
                request_body.interviewee_name,
                request_body.interviewee_email,
                json.dumps(questions),
            )

            await log_audit(
                conn, incident_id, current_user.id,
                "investigation_interview_created", "investigation_interview",
                junction_row["id"],
                {"interviewee_name": request_body.interviewee_name, "interviewee_role": request_body.interviewee_role},
            )

        invite_sent = False
        if request_body.send_invite and request_body.interviewee_email:
            invite_token = secrets.token_urlsafe(32)
            await conn.execute(
                """
                UPDATE ir_investigation_interviews
                SET invite_token = $1, invite_sent_at = NOW()
                WHERE id = $2
                """,
                invite_token, junction_row["id"],
            )
            try:
                company_row = await conn.fetchrow(
                    "SELECT name FROM companies WHERE id = $1", incident["company_id"]
                )
                company_name = company_row["name"] if company_row else "Your Company"
                email_service = get_email_service()
                await email_service.send_investigation_interview_invite_email(
                    to_email=request_body.interviewee_email,
                    to_name=request_body.interviewee_name,
                    company_name=company_name,
                    interviewee_role=request_body.interviewee_role,
                    invite_token=invite_token,
                    custom_message=request_body.custom_message,
                )
                invite_sent = True
            except Exception as e:
                logging.getLogger(__name__).warning("Failed to send investigation invite email: %s", e)

        ws_token = create_interview_ws_token(interview_id)

        return InvestigationInterviewStart(
            investigation_interview_id=junction_row["id"],
            interview_id=interview_id,
            websocket_url=f"/api/ws/interview/{interview_id}",
            ws_auth_token=ws_token,
            questions_generated=questions,
            invite_sent=invite_sent,
        )


@router.post("/{incident_id}/investigation-interviews/batch")
async def batch_create_investigation_interviews(
    incident_id: UUID,
    request_body: list[InvestigationInterviewCreate],
    current_user=Depends(require_admin_or_client),
):
    """Batch-create investigation interviews for an IR incident (max 20)."""
    from app.matcha.services.ir_interview_questions import generate_investigation_questions
    from app.core.services.auth import create_interview_ws_token

    if len(request_body) == 0:
        raise HTTPException(status_code=400, detail="At least one interview must be provided")
    if len(request_body) > 20:
        raise HTTPException(status_code=400, detail="Cannot create more than 20 interviews at once")

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            """
            SELECT id, title, description, incident_type, severity, status, location,
                   occurred_at, witnesses, company_id
            FROM ir_incidents WHERE id = $1
            """,
            incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        if incident["status"] not in ("investigating", "action_required", "reported"):
            raise HTTPException(
                status_code=400,
                detail=f"Incident must be in investigating, action_required, or reported status (current: {incident['status']})",
            )

        prior_rows = await conn.fetch(
            """
            SELECT i.transcript
            FROM ir_investigation_interviews irii
            JOIN interviews i ON irii.interview_id = i.id
            WHERE irii.incident_id = $1 AND i.transcript IS NOT NULL
            ORDER BY irii.created_at
            """,
            incident_id,
        )
        prior_transcripts = [r["transcript"] for r in prior_rows]

        existing_email_rows = await conn.fetch(
            """
            SELECT interviewee_email FROM ir_investigation_interviews
            WHERE incident_id = $1 AND status != 'cancelled' AND interviewee_email IS NOT NULL
            """,
            incident_id,
        )
        existing_emails = {r["interviewee_email"].lower() for r in existing_email_rows}

        company_row = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", incident["company_id"]
        )
        company_name = company_row["name"] if company_row else "Your Company"

        settings = get_settings()
        incident_data = {
            "title": incident["title"],
            "description": incident["description"],
            "incident_type": incident["incident_type"],
            "severity": incident["severity"],
            "location": incident["location"],
            "occurred_at": str(incident["occurred_at"]) if incident["occurred_at"] else None,
        }

        created = []
        failed = []
        seen_emails_this_batch: set[str] = set()

        for item in request_body:
            if item.interviewee_email:
                email_lower = item.interviewee_email.lower()
                if email_lower in existing_emails or email_lower in seen_emails_this_batch:
                    failed.append({
                        "interviewee_name": item.interviewee_name,
                        "interviewee_email": item.interviewee_email,
                        "error": "An active investigation interview already exists for this email address",
                    })
                    continue
                seen_emails_this_batch.add(email_lower)

            try:
                questions = await generate_investigation_questions(
                    incident=incident_data,
                    interviewee_name=item.interviewee_name,
                    interviewee_role=item.interviewee_role,
                    prior_transcripts=prior_transcripts if prior_transcripts else None,
                    api_key=settings.gemini_api_key,
                    model=settings.analysis_model,
                )

                async with conn.transaction():
                    interview_row = await conn.fetchrow(
                        """
                        INSERT INTO interviews (company_id, interview_type, incident_id, er_case_id, interviewee_role, status)
                        VALUES ($1, 'investigation', $2, $3, $4, 'pending')
                        RETURNING id
                        """,
                        incident["company_id"],
                        incident_id,
                        item.er_case_id,
                        item.interviewee_role,
                    )
                    interview_id = interview_row["id"]

                    junction_row = await conn.fetchrow(
                        """
                        INSERT INTO ir_investigation_interviews
                            (incident_id, interview_id, er_case_id, interviewee_role, interviewee_name, interviewee_email, questions_generated, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
                        RETURNING id
                        """,
                        incident_id,
                        interview_id,
                        item.er_case_id,
                        item.interviewee_role,
                        item.interviewee_name,
                        item.interviewee_email,
                        json.dumps(questions),
                    )

                    await log_audit(
                        conn, incident_id, current_user.id,
                        "investigation_interview_created", "investigation_interview",
                        junction_row["id"],
                        {"interviewee_name": item.interviewee_name, "interviewee_role": item.interviewee_role},
                    )

                ws_token = create_interview_ws_token(interview_id)

                invite_sent = False
                if item.send_invite and item.interviewee_email:
                    invite_token = secrets.token_urlsafe(32)
                    await conn.execute(
                        """
                        UPDATE ir_investigation_interviews
                        SET invite_token = $1, invite_sent_at = NOW()
                        WHERE id = $2
                        """,
                        invite_token, junction_row["id"],
                    )
                    try:
                        email_service = get_email_service()
                        await email_service.send_investigation_interview_invite_email(
                            to_email=item.interviewee_email,
                            to_name=item.interviewee_name,
                            company_name=company_name,
                            interviewee_role=item.interviewee_role,
                            invite_token=invite_token,
                            custom_message=item.custom_message,
                        )
                        invite_sent = True
                    except Exception as e:
                        logging.getLogger(__name__).warning("Failed to send investigation invite email: %s", e)

                created.append({
                    "investigation_interview_id": str(junction_row["id"]),
                    "interview_id": str(interview_id),
                    "interviewee_name": item.interviewee_name,
                    "interviewee_email": item.interviewee_email,
                    "websocket_url": f"/api/ws/interview/{interview_id}",
                    "ws_auth_token": ws_token,
                    "questions_generated": questions,
                    "invite_sent": invite_sent,
                })

            except HTTPException:
                raise
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "Failed to create investigation interview for %s: %s", item.interviewee_name, e
                )
                failed.append({
                    "interviewee_name": item.interviewee_name,
                    "interviewee_email": item.interviewee_email,
                    "error": str(e),
                })

        return {
            "created": len(created),
            "failed": len(failed),
            "interviews": created,
            "errors": failed,
        }


@router.post("/{incident_id}/investigation-interviews/{investigation_interview_id}/resend-invite")
async def resend_investigation_interview_invite(
    incident_id: UUID,
    investigation_interview_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Resend an investigation interview invite email."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id, company_id FROM ir_incidents WHERE id = $1", incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        row = await conn.fetchrow(
            """
            SELECT id, status, interviewee_email, interviewee_name, interviewee_role,
                   invite_token, er_case_id
            FROM ir_investigation_interviews
            WHERE id = $1 AND incident_id = $2
            """,
            investigation_interview_id, incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Investigation interview not found")

        if not row["interviewee_email"]:
            raise HTTPException(status_code=400, detail="No email address on file for this interviewee")

        if row["status"] not in ("pending", "in_progress"):
            raise HTTPException(
                status_code=400,
                detail=f"Invite can only be resent for pending or in_progress interviews (current: {row['status']})",
            )

        invite_token = row["invite_token"]
        if not invite_token:
            invite_token = secrets.token_urlsafe(32)
            await conn.execute(
                "UPDATE ir_investigation_interviews SET invite_token = $1 WHERE id = $2",
                invite_token, investigation_interview_id,
            )

        await conn.execute(
            "UPDATE ir_investigation_interviews SET invite_sent_at = NOW() WHERE id = $1",
            investigation_interview_id,
        )

        company_row = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", incident["company_id"]
        )
        company_name = company_row["name"] if company_row else "Your Company"

        try:
            email_service = get_email_service()
            await email_service.send_investigation_interview_invite_email(
                to_email=row["interviewee_email"],
                to_name=row["interviewee_name"],
                company_name=company_name,
                interviewee_role=row["interviewee_role"],
                invite_token=invite_token,
                custom_message=None,
            )
        except Exception as e:
            logger.warning("Failed to resend investigation invite email: %s", e)
            raise HTTPException(status_code=502, detail="Failed to send invite email")

        await log_audit(
            conn, incident_id, current_user.id,
            "investigation_interview_invite_resent", "investigation_interview",
            investigation_interview_id,
            {"interviewee_email": row["interviewee_email"]},
        )

        return {"status": "sent"}


@router.post("/{incident_id}/investigation-interviews/{investigation_interview_id}/generate-link")
async def generate_investigation_interview_link(
    incident_id: UUID,
    investigation_interview_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Generate (or retrieve) an invite link for an investigation interview.

    Ensures a token exists without sending an email, so admins can copy and
    share the link directly (e.g. via Slack, in-person, etc.).
    """
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id, company_id FROM ir_incidents WHERE id = $1", incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        row = await conn.fetchrow(
            """
            SELECT id, status, invite_token
            FROM ir_investigation_interviews
            WHERE id = $1 AND incident_id = $2
            """,
            investigation_interview_id, incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Investigation interview not found")

        if row["status"] in ("cancelled", "completed", "analyzed"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot generate link for {row['status']} interview",
            )

        invite_token = row["invite_token"]
        if not invite_token:
            invite_token = secrets.token_urlsafe(32)
            await conn.execute(
                "UPDATE ir_investigation_interviews SET invite_token = $1 WHERE id = $2",
                invite_token, investigation_interview_id,
            )

        return {"invite_token": invite_token}


@router.get("/{incident_id}/investigation-interviews", response_model=list[InvestigationInterviewResponse])
async def list_investigation_interviews(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """List investigation interviews for an IR incident."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id, company_id FROM ir_incidents WHERE id = $1", incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        rows = await conn.fetch(
            """
            SELECT irii.id, irii.incident_id, irii.interview_id, irii.er_case_id,
                   irii.interviewee_role, irii.interviewee_name, irii.interviewee_email,
                   irii.questions_generated, irii.status, irii.created_at, irii.completed_at,
                   irii.invite_token, irii.invite_sent_at,
                   i.transcript IS NOT NULL as has_transcript,
                   i.investigation_analysis
            FROM ir_investigation_interviews irii
            JOIN interviews i ON irii.interview_id = i.id
            WHERE irii.incident_id = $1
            ORDER BY irii.created_at DESC
            """,
            incident_id,
        )

        results = []
        for row in rows:
            analysis = row["investigation_analysis"]
            if isinstance(analysis, str):
                analysis = json.loads(analysis)
            questions = row["questions_generated"]
            if isinstance(questions, str):
                questions = json.loads(questions)
            results.append(InvestigationInterviewResponse(
                id=row["id"],
                incident_id=row["incident_id"],
                interview_id=row["interview_id"],
                er_case_id=row["er_case_id"],
                interviewee_role=row["interviewee_role"],
                interviewee_name=row["interviewee_name"],
                interviewee_email=row["interviewee_email"],
                questions_generated=questions,
                status=row["status"],
                has_transcript=row["has_transcript"],
                investigation_analysis=analysis,
                invite_token=row["invite_token"],
                invite_sent_at=row["invite_sent_at"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            ))
        return results


@router.delete("/{incident_id}/investigation-interviews/{investigation_interview_id}")
async def cancel_investigation_interview(
    incident_id: UUID,
    investigation_interview_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Cancel a pending investigation interview."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id, company_id FROM ir_incidents WHERE id = $1", incident_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        if current_user.role != "admin" and incident["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Incident not found")

        row = await conn.fetchrow(
            """
            SELECT id, status FROM ir_investigation_interviews
            WHERE id = $1 AND incident_id = $2
            """,
            investigation_interview_id, incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Investigation interview not found")
        if row["status"] not in ("pending",):
            raise HTTPException(status_code=400, detail="Only pending interviews can be cancelled")

        await conn.execute(
            "UPDATE ir_investigation_interviews SET status = 'cancelled' WHERE id = $1",
            investigation_interview_id,
        )
        await conn.execute(
            "UPDATE interviews SET status = 'cancelled' WHERE id = (SELECT interview_id FROM ir_investigation_interviews WHERE id = $1)",
            investigation_interview_id,
        )

        await log_audit(
            conn, incident_id, current_user.id,
            "investigation_interview_cancelled", "investigation_interview",
            investigation_interview_id, {},
        )

        return {"status": "cancelled"}
