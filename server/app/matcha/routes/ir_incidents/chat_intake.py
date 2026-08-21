"""Conversational incident-intake — optional "chat it in" alternative to the
create wizard.

POST /ir/incidents/chat/turn — stateless per-turn REST endpoint. The client
holds the transcript + accumulated fields and echoes both each turn; the
server makes one Gemini flash-lite call and returns the next assistant
message plus the merged field state. Never creates the incident — the client
lands on the create wizard's review step and submits via POST /ir/incidents
as normal, same as voice dictation.

Gated by BOTH the router-level ``incidents`` feature (parent mount) AND a
per-route ``ir_chat_intake`` feature (admin-toggle, default off). 2-segment
path so it isn't shadowed by crud's ``/{incident_id}``.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_connection
from app.core.services.redis_cache import check_rate_limit
from app.matcha.dependencies import require_admin_or_client, get_client_company_id, require_feature
from app.matcha.models.ir.chat_intake import ChatIntakeTurnRequest, ChatIntakeTurnResponse
from app.matcha.services.ir.ir_chat_intake import MAX_TURNS, next_turn
from ._shared import _location_label

router = APIRouter()


@router.post("/chat/turn", response_model=ChatIntakeTurnResponse)
async def chat_intake_turn(
    body: ChatIntakeTurnRequest,
    current_user=Depends(require_admin_or_client),
    _gate=Depends(require_feature("ir_chat_intake")),
):
    # Fires roughly once per conversational turn rather than once per report
    # (like voice parse), so the buckets are wider than voice's.
    user_key = f"user:{current_user.id}"
    await check_rate_limit(user_key, "ir_chat_intake_burst", 20, 60)
    await check_rate_limit(user_key, "ir_chat_intake", 120, 3600)

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    await check_rate_limit(str(company_id), "ir_chat_intake_co", 600, 3600)

    turn_count = len(body.transcript)
    if turn_count >= MAX_TURNS * 2:
        return ChatIntakeTurnResponse(
            assistant_message="Let's finish this one in the form below.",
            fields=body.known_fields,
            complete=True,
            turn_count=turn_count,
        )

    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, name, city, state FROM business_locations
               WHERE company_id = $1 AND COALESCE(is_active, true) = true
               ORDER BY name NULLS LAST, city""",
            company_id,
        )
    location_options = [
        {"id": str(r["id"]), "label": _location_label(r["name"], r["city"], r["state"])} for r in rows
    ]

    result = await next_turn(
        [m.model_dump() for m in body.transcript],
        body.known_fields.model_dump(),
        location_options=location_options,
    )
    return ChatIntakeTurnResponse(**result, turn_count=turn_count)
