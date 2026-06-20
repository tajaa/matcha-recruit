"""Push-notification device registration.

iOS clients register their APNs device token here after the user grants
notification permission; the token is upserted against the authenticated user so
`apns_service.send_to_user` can fan a bell notification out to their devices.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import get_current_user
from ..models.auth import CurrentUser

router = APIRouter()


class DeviceTokenBody(BaseModel):
    token: str
    platform: str = "ios"
    bundle_id: Optional[str] = None


class UnregisterBody(BaseModel):
    token: str


@router.post("/register")
async def register_device(
    body: DeviceTokenBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upsert a device token for the current user (idempotent on token)."""
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO device_tokens (user_id, token, platform, bundle_id, last_seen_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (token) DO UPDATE
              SET user_id = EXCLUDED.user_id,
                  platform = EXCLUDED.platform,
                  bundle_id = EXCLUDED.bundle_id,
                  last_seen_at = NOW()
            """,
            current_user.id, body.token, body.platform, body.bundle_id,
        )
    return {"ok": True}


@router.post("/unregister")
async def unregister_device(
    body: UnregisterBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Drop a device token on logout so a shared device stops getting the
    previous user's pushes."""
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM device_tokens WHERE token = $1 AND user_id = $2",
            body.token, current_user.id,
        )
    return {"ok": True}
