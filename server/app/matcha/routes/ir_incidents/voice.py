"""Voice incident-intake — optional "talk it in" parse for the IR create form.

POST /ir/incidents/voice/parse — accepts a WAV recording, Gemini transcribes +
extracts the create-form fields, returns the prefill (does NOT create the incident;
the user reviews + submits via POST /ir/incidents as normal).

Gated by BOTH the router-level ``incidents`` feature (parent mount) AND a per-route
``ir_voice_intake`` feature (admin-toggle, default off). 2-segment path so it isn't
shadowed by crud's ``/{incident_id}``.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.database import get_connection
from app.core.services.redis_cache import check_rate_limit
from app.matcha.dependencies import require_admin_or_client, get_client_company_id, require_feature
from app.matcha.services.ir_voice_parser import parse_voice_incident
from ._shared import _read_audio_or_400

router = APIRouter()


def _loc_label(r) -> str:
    geo = ", ".join(p for p in (r["city"], r["state"]) if p)
    return " — ".join(p for p in (r["name"], geo) if p) or "Location"


@router.post("/voice/parse")
async def parse_voice(
    file: UploadFile = File(...),
    current_user=Depends(require_admin_or_client),
    _gate=Depends(require_feature("ir_voice_intake")),
):
    # Each parse is an expensive Gemini multimodal call. Keyed on the user, not
    # client IP — an office NAT puts a whole company behind one address, so a
    # per-IP bucket let one heavy user starve everyone else's quota. Burst
    # guard (5/min) catches retry loops; hourly cap (40/hr) bounds sustained
    # per-user abuse. Checked before reading the upload so a 429 short-circuits
    # cheaply.
    user_key = f"user:{current_user.id}"
    await check_rate_limit(user_key, "ir_voice_parse_burst", 5, 60)
    await check_rate_limit(user_key, "ir_voice_parse", 40, 3600)

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    # Same action key as the public per-company budget in inbound_email.py's
    # _voice_parse_budget — authed and public voice-parse share one hourly
    # Gemini budget per company, regardless of how many distinct users hit it.
    await check_rate_limit(str(company_id), "ir_voice_parse_co", 120, 3600)
    audio = await _read_audio_or_400(file)

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
