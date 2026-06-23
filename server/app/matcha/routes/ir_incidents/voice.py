"""Voice incident-intake — optional "talk it in" parse for the IR create form.

POST /ir/incidents/voice/parse — accepts a WAV recording, Gemini transcribes +
extracts the create-form fields, returns the prefill (does NOT create the incident;
the user reviews + submits via POST /ir/incidents as normal).

Gated by BOTH the router-level ``incidents`` feature (parent mount) AND a per-route
``ir_voice_intake`` feature (admin-toggle, default off). 2-segment path so it isn't
shadowed by crud's ``/{incident_id}``.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.database import get_connection
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.matcha.dependencies import require_admin_or_client, get_client_company_id, require_feature
from app.matcha.services.ir_voice_parser import parse_voice_incident

router = APIRouter()

_ALLOWED_AUDIO_MIME = {"audio/wav", "audio/x-wav", "audio/wave"}
_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # ~13 min of 16kHz mono 16-bit WAV


def _loc_label(r) -> str:
    geo = ", ".join(p for p in (r["city"], r["state"]) if p)
    return " — ".join(p for p in (r["name"], geo) if p) or "Location"


@router.post("/voice/parse")
async def parse_voice(
    request: Request,
    file: UploadFile = File(...),
    current_user=Depends(require_admin_or_client),
    _gate=Depends(require_feature("ir_voice_intake")),
):
    # Each parse is an expensive Gemini multimodal call. Throttle per client IP so a
    # glitchy/retrying browser or a malicious authed user can't hammer it. Burst guard
    # (5/min) catches retry loops; hourly cap (40/hr) bounds sustained abuse. Checked
    # before reading the upload so a 429 short-circuits cheaply.
    ip = client_ip(request)
    await check_rate_limit(ip, "ir_voice_parse_burst", 5, 60)
    await check_rate_limit(ip, "ir_voice_parse", 40, 3600)

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    if (file.content_type or "").lower() not in _ALLOWED_AUDIO_MIME:
        raise HTTPException(status_code=400, detail="Unsupported audio format — expected WAV.")
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    if len(audio) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large (max 25MB).")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, name, city, state FROM business_locations
               WHERE company_id = $1 AND COALESCE(is_active, true) = true
               ORDER BY name NULLS LAST, city""",
            company_id,
        )
    location_options = [{"id": str(r["id"]), "label": _loc_label(r)} for r in rows]
    return await parse_voice_incident(audio, (file.content_type or "audio/wav").lower(),
                                      location_options=location_options)
