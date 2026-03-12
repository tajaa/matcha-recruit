"""Public investigation interview invite endpoints (no auth required)."""

from fastapi import APIRouter, HTTPException
from app.database import get_connection
from app.core.services.auth import create_interview_ws_token

router = APIRouter()


# ============================================================================
# Public endpoints (no auth - invite_token-based access)
# ============================================================================


@router.get("/investigation/{token}")
async def get_investigation_invite_info(token: str):
    """Get public info for an investigation interview invite link."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT ii.interviewee_name, ii.interviewee_role, ii.status,
                   i.incident_type, co.name as company_name
            FROM ir_investigation_interviews ii
            JOIN ir_incidents i ON ii.incident_id = i.id
            JOIN companies co ON i.company_id = co.id
            WHERE ii.invite_token = $1
            """,
            token,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invalid or expired link")

        if row["status"] == "cancelled":
            raise HTTPException(status_code=410, detail="This interview has been cancelled")

        return {
            "interviewee_name": row["interviewee_name"],
            "interviewee_role": row["interviewee_role"],
            "company_name": row["company_name"],
            "incident_type": row["incident_type"],
            "status": row["status"],
        }


@router.post("/investigation/{token}/start")
async def start_investigation_interview(token: str):
    """Start an investigation interview via invite token."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT ii.id, ii.status, ii.interview_id
            FROM ir_investigation_interviews ii
            WHERE ii.invite_token = $1
            """,
            token,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invalid or expired link")

        if row["status"] == "cancelled":
            raise HTTPException(status_code=410, detail="This interview has been cancelled")

        # Allow re-viewing a completed interview
        if row["status"] in ("completed", "analyzed"):
            return {"status": "completed"}

        interview_id = row["interview_id"]
        ws_token = create_interview_ws_token(interview_id)

        # Update junction row to in_progress only if currently pending (idempotent)
        await conn.execute(
            """
            UPDATE ir_investigation_interviews
            SET status = 'in_progress'
            WHERE invite_token = $1 AND status = 'pending'
            """,
            token,
        )

        # Update interview record to in_progress only if currently pending
        await conn.execute(
            """
            UPDATE interviews
            SET status = 'in_progress'
            WHERE id = $1 AND status = 'pending'
            """,
            interview_id,
        )

        return {
            "interview_id": str(interview_id),
            "websocket_url": f"/api/ws/interview/{interview_id}",
            "ws_auth_token": ws_token,
            "status": "started",
        }
