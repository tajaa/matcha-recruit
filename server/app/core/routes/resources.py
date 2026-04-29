"""Resources hub — public endpoints for HR resource downloads + lead capture."""

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from ...database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Asset registry — slug -> public download path. Files live in client/public/
# and are served from the static frontend root, so download_url is absolute
# from the site root.
# ---------------------------------------------------------------------------

ASSETS: dict[str, dict[str, str]] = {
    "offer-letter-docx": {"path": "/templates/offer-letter.docx", "name": "Offer Letter (DOCX)"},
    "offer-letter-pdf": {"path": "/templates/offer-letter.pdf", "name": "Offer Letter (PDF)"},
    "job-descriptions-library": {"path": "/templates/job-descriptions-library.docx", "name": "Job Descriptions Library"},
    "pip": {"path": "/templates/pip.docx", "name": "Performance Improvement Plan"},
    "termination-checklist": {"path": "/templates/termination-checklist.pdf", "name": "Termination Checklist"},
    "i9-w4-packet": {"path": "/templates/i9-w4-packet.pdf", "name": "I-9 / W-4 Packet"},
    "interview-scorecard": {"path": "/templates/interview-scorecard.docx", "name": "Interview Scorecard"},
    "interview-guide": {"path": "/templates/interview-guide.docx", "name": "Interview Guide — What You Can & Can't Ask"},
    "pto-policy": {"path": "/templates/pto-policy.docx", "name": "PTO Policy Template"},
    "workplace-investigation-report": {"path": "/templates/workplace-investigation-report.docx", "name": "Workplace Investigation Report"},
}


# ---------------------------------------------------------------------------
# In-process rate limit per IP. Mirrors newsletter.py pattern.
# ---------------------------------------------------------------------------

_LEAD_WINDOW_SECONDS = 60
_LEAD_MAX_PER_WINDOW = 15
_lead_state: dict[str, list[float]] = {}


def _rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - _LEAD_WINDOW_SECONDS
    timestamps = [t for t in _lead_state.get(client_ip, []) if t >= cutoff]
    if len(timestamps) >= _LEAD_MAX_PER_WINDOW:
        _lead_state[client_ip] = timestamps
        return True
    timestamps.append(now)
    _lead_state[client_ip] = timestamps
    if len(_lead_state) > 1000:
        for ip in list(_lead_state.keys()):
            if not _lead_state[ip] or _lead_state[ip][-1] < cutoff:
                _lead_state.pop(ip, None)
    return False


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class LeadCaptureRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    asset_slug: str
    source: Optional[str] = "resources"
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


@router.post("/lead-capture")
async def lead_capture(body: LeadCaptureRequest, request: Request):
    """Capture an email in exchange for a download URL.

    Single-step (no double opt-in) — these are template downloads, not
    newsletter subscriptions. Returns the public download URL on success.
    """
    if _rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")

    asset = ASSETS.get(body.asset_slug)
    if not asset:
        raise HTTPException(status_code=404, detail="Unknown asset")

    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO lead_captures
               (email, name, asset_slug, source, utm_source, utm_medium, utm_campaign, ip_address)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            body.email.lower().strip(),
            body.name.strip() if body.name else None,
            body.asset_slug,
            body.source or "resources",
            body.utm_source,
            body.utm_medium,
            body.utm_campaign,
            _client_ip(request),
        )

    logger.info("Lead capture: %s -> %s", body.email, body.asset_slug)

    return {
        "ok": True,
        "download_url": asset["path"],
        "asset_name": asset["name"],
    }


@router.get("/assets")
async def list_assets():
    """List available downloadable assets — used by the frontend Templates page."""
    return {"assets": [{"slug": k, **v} for k, v in ASSETS.items()]}
