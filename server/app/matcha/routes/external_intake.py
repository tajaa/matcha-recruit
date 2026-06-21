"""Public off-platform client-intake (`/external-intake/{token}`).

No auth — a prospect opens a broker's shareable link and self-completes the EPL
questionnaire without onboarding (WTW p.11). Token-gated, locked once completed
or expired. Answers are attributed to the broker who minted the link.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...database import get_connection
from ..services import external_clients as ext

router = APIRouter()


class IntakeSubmit(BaseModel):
    # {factor_key: status}; status validated against the EPL status set in the service
    epl: dict[str, str] = Field(default_factory=dict)


def _state(row: dict) -> str:
    if row["is_open"]:
        return "open"
    return "completed" if row["status"] == "completed" else "expired"


@router.get("/{token}")
async def get_intake(token: str):
    async with get_connection() as conn:
        row = await ext.get_intake(conn, token)
    if not row:
        raise HTTPException(status_code=404, detail="Invalid or unknown link")
    return {
        "state": _state(row),
        "client_name": row["client_name"],
        "factors": ext.intake_factors(),
    }


@router.post("/{token}")
async def submit_intake(token: str, body: IntakeSubmit):
    async with get_connection() as conn:
        row = await ext.get_intake(conn, token)
        if not row:
            raise HTTPException(status_code=404, detail="Invalid or unknown link")
        if not row["is_open"]:
            raise HTTPException(status_code=409, detail="This link is no longer active")
        await ext.complete_intake(conn, row, body.epl, None)
    return {"status": "completed"}
