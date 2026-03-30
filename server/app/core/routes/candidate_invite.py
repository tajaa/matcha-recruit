"""Public candidate interview invite endpoints (no auth required)."""

import json

from fastapi import APIRouter, HTTPException
from app.database import get_connection
from app.core.services.auth import create_interview_ws_token

router = APIRouter()


@router.get("/candidate-interview/{token}")
async def get_candidate_invite_info(token: str):
    """Get public info for a candidate interview invite link."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT i.id, i.status, i.raw_culture_data
            FROM interviews i
            WHERE i.raw_culture_data->>'invite_token' = $1
              AND i.interview_type = 'screening'
            """,
            token,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invalid or expired link")

        if row["status"] == "cancelled":
            raise HTTPException(status_code=410, detail="This interview has been cancelled")

        raw = row["raw_culture_data"]
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})

        return {
            "candidate_name": data.get("candidate_name"),
            "position_title": data.get("position_title"),
            "company_name": data.get("company_name"),
            "status": row["status"],
        }


@router.post("/candidate-interview/{token}/start")
async def start_candidate_interview(token: str):
    """Start a candidate interview via invite token."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT i.id, i.status
            FROM interviews i
            WHERE i.raw_culture_data->>'invite_token' = $1
              AND i.interview_type = 'screening'
            """,
            token,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invalid or expired link")

        if row["status"] == "cancelled":
            raise HTTPException(status_code=410, detail="This interview has been cancelled")

        if row["status"] in ("completed", "analyzed"):
            return {"status": "completed"}

        interview_id = row["id"]
        ws_token = create_interview_ws_token(interview_id)

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
