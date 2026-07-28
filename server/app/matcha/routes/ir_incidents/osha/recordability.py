"""Per-incident OSHA recordability: the manual classification update and the
Gemini-backed determination assist.
"""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir.osha import OshaRecordabilityUpdate
from app.core.services.genai_client import get_genai_client
from ._shared import _safe_json_loads

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_OSHA_CLASSIFICATIONS = {
    "death", "days_away", "restricted_duty",
    "medical_treatment", "loss_of_consciousness", "significant_injury",
}


@router.put("/{incident_id}/osha")
async def update_osha_recordability(
    incident_id: UUID,
    update: OshaRecordabilityUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Set OSHA recordability determination for an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    if update.osha_classification and update.osha_classification not in VALID_OSHA_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OSHA classification. Must be one of: {', '.join(sorted(VALID_OSHA_CLASSIFICATIONS))}",
        )

    if update.wc_claim_type is not None and update.wc_claim_type not in ("acute", "cumulative_trauma", "unknown"):
        raise HTTPException(
            status_code=400,
            detail="Invalid wc_claim_type. Must be one of: acute, cumulative_trauma, unknown",
        )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM ir_incidents WHERE id = $1 AND company_id = $2",
            str(incident_id), company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        sets = ["osha_recordable = $3"]
        params = [str(incident_id), company_id, update.osha_recordable]
        idx = 4

        if update.osha_classification is not None:
            sets.append(f"osha_classification = ${idx}")
            params.append(update.osha_classification)
            idx += 1
        if update.osha_case_number is not None:
            sets.append(f"osha_case_number = ${idx}")
            params.append(update.osha_case_number)
            idx += 1
        if update.days_away_from_work is not None:
            sets.append(f"days_away_from_work = ${idx}")
            params.append(update.days_away_from_work)
            idx += 1
        if update.days_restricted_duty is not None:
            sets.append(f"days_restricted_duty = ${idx}")
            params.append(update.days_restricted_duty)
            idx += 1
        # WC claim depth (wcdeep01).
        if update.wc_claim_type is not None:
            sets.append(f"wc_claim_type = ${idx}")
            params.append(update.wc_claim_type)
            idx += 1
        if update.post_termination is not None:
            sets.append(f"post_termination = ${idx}")
            params.append(update.post_termination)
            idx += 1
        if update.return_to_work_date is not None:
            sets.append(f"return_to_work_date = ${idx}")
            params.append(update.return_to_work_date)
            idx += 1

        updated = await conn.fetchrow(
            f"UPDATE ir_incidents SET {', '.join(sets)} WHERE id = $1 AND company_id = $2 RETURNING *",
            *params,
        )
        # Recordability set outside the Copilot chain (manual override) still
        # needs the OSHA Privacy Case question. Emit the per-employee privacy
        # card into the transcript so it's pending next time the Copilot opens —
        # otherwise masking would fall to the safety net alone (which can't catch
        # the human-only opt-out). Idempotent + no-op if already asked/answered.
        if update.osha_recordable is True:
            # Lazy: avoid a circular import. Absolute, not `.copilot` — this file
            # moved into the osha/ subpackage, where a 1-dot relative resolves to
            # `ir_incidents.osha.copilot`, which does not exist. The UPDATE above
            # has already committed by this point, so the ModuleNotFoundError
            # surfaced as an unhandled 500 on a write that had actually succeeded.
            from app.matcha.routes.ir_incidents.copilot import ensure_case_chain
            await ensure_case_chain(conn, str(incident_id), current_user)
        return {"message": "OSHA recordability updated", "id": str(updated["id"])}


@router.post("/{incident_id}/osha/determine")
async def osha_ai_determination(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """AI-assisted OSHA recordability determination using Gemini."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ir_incidents WHERE id = $1 AND company_id = $2",
            str(incident_id), company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        category_data = _safe_json_loads(row.get("category_data"), {})

        prompt = f"""Analyze this workplace incident for OSHA recordability.

Incident: {row['title']}
Description: {row['description']}
Type: {row['incident_type']}
Severity: {row['severity']}
Injury type: {category_data.get('injury_type', 'unknown')}
Body parts: {category_data.get('body_parts', [])}
Treatment: {category_data.get('treatment', 'unknown')}
Lost days: {category_data.get('lost_days', 0)}

OSHA recordability criteria (29 CFR 1904):
- Death
- Days away from work
- Restricted work or transfer to another job
- Medical treatment beyond first aid
- Loss of consciousness
- Significant injury or illness diagnosed by a physician

Respond in JSON:
{{"recordable": true/false, "classification": "death|days_away|restricted_duty|medical_treatment|loss_of_consciousness|significant_injury|not_recordable", "reasoning": "brief explanation"}}
"""

        settings = get_settings()
        try:
            client = get_genai_client()
            response = await client.aio.models.generate_content(
                model=settings.analysis_model,
                contents=prompt,
            )
            text = (response.text or "").strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(text)
        except Exception as e:
            logger.error("OSHA AI determination failed: %s", e)
            raise HTTPException(status_code=500, detail="AI determination failed")

        return {
            "incident_id": str(incident_id),
            "recordable": result.get("recordable", False),
            "classification": result.get("classification", "not_recordable"),
            "reasoning": result.get("reasoning", ""),
        }
