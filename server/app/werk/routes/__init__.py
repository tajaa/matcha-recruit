"""Werk route aggregation.

`werk_router` carries the same prefixes these routers had under `core_router`,
so mounting it at `/api` in `main.py` leaves every URL unchanged. The WS router
is exported separately because it mounts at `/ws/channels`, not under `/api`.
"""

from fastapi import APIRouter

from .inbox import router as inbox_router
from .channels import router as channels_router
from .channels_ws import router as channels_ws_router
from .channel_job_postings import router as channel_job_postings_router
from .channel_broadcasts import router as channel_broadcasts_router, webhook_router as livekit_webhook_router
from .channel_calls import router as channel_calls_router

werk_router = APIRouter()

werk_router.include_router(inbox_router, prefix="/inbox", tags=["inbox"])
werk_router.include_router(channels_router, prefix="/channels", tags=["channels"])
werk_router.include_router(channel_job_postings_router, prefix="/channels", tags=["channel-job-postings"])
werk_router.include_router(channel_broadcasts_router, prefix="/channels", tags=["channel-broadcasts"])
werk_router.include_router(channel_calls_router, prefix="/channels", tags=["channel-calls"])
werk_router.include_router(livekit_webhook_router, prefix="/webhooks", tags=["livekit-webhook"])

__all__ = [
    "werk_router",
    "channels_ws_router",
    "inbox_router",
    "channels_router",
    "channel_job_postings_router",
    "channel_broadcasts_router",
    "channel_calls_router",
    "livekit_webhook_router",
]
