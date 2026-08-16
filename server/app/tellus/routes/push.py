"""Tell-Us push-notification device registration.

iOS clients register their APNs device token here after the user grants
notification permission; the token is upserted against the authenticated
Tell-Us account so `services/push.send_to_accounts` can fan a bell
notification out to their devices.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..dependencies import require_tellus_account
from ..models.tellus import TellusAccount
from ..services import push

router = APIRouter()


class DeviceTokenBody(BaseModel):
    token: str
    platform: str = "ios"
    bundle_id: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)


class DeviceLocationBody(BaseModel):
    token: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class UnregisterBody(BaseModel):
    token: str


@router.post("/push/register")
async def register_device(
    body: DeviceTokenBody,
    account: TellusAccount = Depends(require_tellus_account),
):
    """Upsert a device token for the current account (idempotent on token)."""
    await push.register_token(
        account.id, body.token, body.platform, body.bundle_id, body.latitude, body.longitude
    )
    return {"ok": True}


@router.post("/push/location")
async def update_device_location(
    body: DeviceLocationBody,
    account: TellusAccount = Depends(require_tellus_account),
):
    await push.update_location(account.id, body.token, body.latitude, body.longitude)
    return {"ok": True}


@router.post("/push/unregister")
async def unregister_device(
    body: UnregisterBody,
    account: TellusAccount = Depends(require_tellus_account),
):
    """Drop a device token on logout so a shared device stops getting the
    previous account's pushes."""
    await push.unregister_token(account.id, body.token)
    return {"ok": True}
